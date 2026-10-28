import asyncio
import getpass
import json
import sys
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any, NoReturn

import structlog
from cyclopts import App, Parameter
from rich.console import Console
from rich.table import Table

from app.modules.identity.adapters.claim.unwired_existing_data_claim import (
    UnwiredExistingDataClaim,
)
from app.platform.config import get_identity_cli_settings
from app.shared_kernel.access_guard import DenyAllAccessGuard
from app.shared_kernel.errors import DomainError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.identity.application.user_listing import UserListing
    from app.modules.identity.domain.user import User
    from app.modules.identity.ports.existing_data_claim import ExistingDataClaim
    from app.modules.identity.ports.password_hasher import PasswordHasher
    from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
    from app.shared_kernel.access_guard import AccessGuard

logger = structlog.get_logger(__name__)

identity_app = App(name="identity", help="Manage accounts.")


_guard: AccessGuard = DenyAllAccessGuard()


def use_access_guard(guard: AccessGuard) -> None:
    """Choose the guard the commands check the system actor against."""
    global _guard
    _guard = guard


ClaimBuilder = Callable[["AsyncSession"], "ExistingDataClaim"]


def _no_claim(_session: AsyncSession) -> ExistingDataClaim:
    return UnwiredExistingDataClaim()


_claim_builder: ClaimBuilder = _no_claim


def use_existing_data_claim(builder: ClaimBuilder) -> None:
    """Choose how first-run setup claims existing content (wired by the entrypoint).

    Identity cannot import the modules that own that content, so the CLI
    entrypoint supplies a builder that runs on the setup session.
    """
    global _claim_builder
    _claim_builder = builder


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _read_password(*, use_settings: bool = True) -> str:
    """Read the password from settings (env or secret file) or a hidden prompt.

    With `use_settings` false it always prompts. Never printed or logged.
    """
    configured = get_identity_cli_settings().initial_password if use_settings else None
    if configured is not None and configured.get_secret_value():
        return configured.get_secret_value()
    first = getpass.getpass("Password: ")
    if getpass.getpass("Confirm password: ") != first:
        _fail("The passwords do not match.")
    return first


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run a use case, turning a refusal into a plain message and exit code 1."""
    try:
        return asyncio.run(coroutine)
    except DomainError as error:
        _fail(str(error))


def _hasher() -> PasswordHasher:
    from app.modules.identity.adapters.api.dependencies import get_password_hasher

    return get_password_hasher()


@identity_app.command
def create_admin(*, username: str, display_name: str | None = None) -> None:
    """Create an administrator account.

    With no accounts yet this is first-run setup: it also hands existing content
    to the new administrator. Otherwise it adds another administrator, who must
    change the initial password at first sign-in.

    Args:
        username: Username for the new account.
        display_name: Name shown in the app; defaults to the username.
    """
    password = _read_password()
    name = display_name or username

    async def _create() -> str:
        from app.modules.identity.adapters.persistence.unit_of_work import (
            create_identity_uow_on_session,
        )
        from app.modules.identity.adapters.security.session_token_generator import (
            SecretsSessionTokenGenerator,
        )
        from app.modules.identity.application.create_user import (
            CreateUser,
            CreateUserCommand,
        )
        from app.modules.identity.application.setup_first_admin import (
            SetupFirstAdmin,
            SetupFirstAdminCommand,
        )
        from app.modules.identity.domain.user import Role
        from app.platform.config import get_identity_settings
        from app.platform.database import get_session_factory
        from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR

        hasher = _hasher()
        async with get_session_factory()() as session:
            uow = create_identity_uow_on_session(session)
            async with uow as repos:
                first_run = await repos.users.count() == 0
            if not first_run:
                user = await CreateUser(uow, _guard, hasher).handle(
                    CreateUserCommand(
                        username=username,
                        display_name=name,
                        password=password,
                        role=Role.ADMIN,
                    ),
                    SYSTEM_ACTOR,
                )
                return (
                    f"Created administrator '{user.username}'. "
                    + "They must change the password at first sign-in."
                )
            ttl = timedelta(hours=get_identity_settings().session_ttl_hours)
            result = await SetupFirstAdmin(
                uow,
                _guard,
                hasher,
                SecretsSessionTokenGenerator(),
                _claim_builder(session),
                session_ttl=ttl,
            ).handle(
                SetupFirstAdminCommand(
                    username=username, display_name=name, password=password
                ),
                ANONYMOUS_ACTOR,
            )
            claimed = ", ".join(
                f"{count} {kind}" for kind, count in result.claim.counts.items()
            )
            suffix = f" They now own: {claimed}." if claimed else ""
            return f"Created administrator '{result.user.username}'.{suffix}"

    print(_run(_create()))


@identity_app.command
def reset_password(
    *,
    username: str,
    from_settings: Annotated[
        bool, Parameter(name="--from-settings", negative="")
    ] = False,
) -> None:
    """Give an account a new initial password and end its sessions.

    Always asks for the password (hidden, confirmed) unless `--from-settings`
    is given, so a bootstrap password left in the environment or a secret file
    is never applied to an account by accident.

    Args:
        username: Username of the account to reset.
        from_settings: Read the password from
            MENAGERIST_IDENTITY_INITIAL_PASSWORD or the
            secret file instead of prompting.
    """
    password = _read_password(use_settings=from_settings)

    async def _reset() -> str:
        from app.modules.identity.adapters.persistence.unit_of_work import (
            create_identity_uow_on_session,
        )
        from app.modules.identity.application.reset_password import (
            ResetPassword,
            ResetPasswordCommand,
        )
        from app.modules.identity.domain.errors import UserNotFoundError
        from app.platform.database import get_session_factory
        from app.shared_kernel.actor import SYSTEM_ACTOR

        async with get_session_factory()() as session:
            uow = create_identity_uow_on_session(session)
            async with uow as repos:
                user = await repos.users.get_by_username(username)
            if user is None:
                raise UserNotFoundError("That account does not exist.")
            await ResetPassword(uow, _guard, _hasher()).handle(
                ResetPasswordCommand(user_id=user.id, password=password),
                SYSTEM_ACTOR,
            )
            return (
                f"Password reset for '{user.username}'. "
                + "They must change it at next sign-in."
            )

    print(_run(_reset()))


async def _find_user(uow: IdentityUnitOfWork, username: str) -> User:
    from app.modules.identity.domain.errors import UserNotFoundError

    async with uow as repos:
        user = await repos.users.get_by_username(username)
    if user is None:
        raise UserNotFoundError("That account does not exist.")
    return user


@identity_app.command
def set_display_name(*, username: str, display_name: str) -> None:
    """Change the name an account is shown as.

    Args:
        username: Username of the account.
        display_name: The new display name.
    """

    async def _rename() -> str:
        from app.modules.identity.adapters.persistence.unit_of_work import (
            create_identity_uow_on_session,
        )
        from app.modules.identity.application.update_user import (
            UpdateUser,
            UpdateUserCommand,
        )
        from app.platform.database import get_session_factory
        from app.shared_kernel.actor import SYSTEM_ACTOR

        async with get_session_factory()() as session:
            uow = create_identity_uow_on_session(session)
            user = await _find_user(uow, username)
            updated = await UpdateUser(uow, _guard).handle(
                UpdateUserCommand(user_id=user.id, display_name=display_name),
                SYSTEM_ACTOR,
            )
            name = updated.user.display_name
            return f"Display name for '{user.username}' is now '{name}'."

    print(_run(_rename()))


@identity_app.command
def unlock(*, username: str) -> None:
    """Lift an account's sign-in lockout (it stays enabled or disabled as it was).

    Args:
        username: Username of the account to unlock.
    """

    async def _unlock() -> str:
        from app.modules.identity.adapters.persistence.unit_of_work import (
            create_identity_uow_on_session,
        )
        from app.modules.identity.application.unlock_user import (
            UnlockUser,
            UnlockUserCommand,
        )
        from app.platform.database import get_session_factory
        from app.shared_kernel.actor import SYSTEM_ACTOR

        async with get_session_factory()() as session:
            uow = create_identity_uow_on_session(session)
            user = await _find_user(uow, username)
            await UnlockUser(uow, _guard).handle(
                UnlockUserCommand(user_id=user.id), SYSTEM_ACTOR
            )
            return f"Sign-in lockout cleared for '{user.username}'."

    print(_run(_unlock()))


def _local(moment: datetime | None) -> str:
    return "never" if moment is None else moment.astimezone().strftime("%Y-%m-%d %H:%M")


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


@identity_app.command(name="list")
def list_accounts(
    *, json_output: Annotated[bool, Parameter(name="--json", negative="")] = False
) -> None:
    """List every account: username, display name, role, status and last sign-in.

    Args:
        json_output: Print machine-readable JSON instead of a table.
    """

    async def _list() -> list[UserListing]:
        from app.modules.identity.adapters.persistence.unit_of_work import (
            build_identity_repos,
        )
        from app.modules.identity.application.list_users import (
            ListUsers,
            ListUsersQuery,
        )
        from app.platform.database import get_session_factory
        from app.shared_kernel.actor import SYSTEM_ACTOR

        async with get_session_factory()() as session:
            return await ListUsers(build_identity_repos(session), _guard).handle(
                ListUsersQuery(), SYSTEM_ACTOR
            )

    listings = _run(_list())
    if json_output:
        print(
            json.dumps(
                [
                    {
                        "id": str(item.user.id),
                        "username": item.user.username,
                        "display_name": item.user.display_name,
                        "role": item.user.role.value,
                        "status": "disabled" if item.user.disabled else "active",
                        "last_login_at": _iso(item.user.last_login_at),
                        "locked_until": _iso(item.locked_until),
                    }
                    for item in listings
                ],
                indent=2,
            )
        )
        return
    table = Table("Username", "Display name", "Role", "Status", "Last sign-in")
    for item in listings:
        user = item.user
        status = "disabled" if user.disabled else "active"
        if item.locked_until is not None:
            status += " (locked)"
        table.add_row(
            user.username,
            user.display_name,
            user.role.value,
            status,
            _local(user.last_login_at),
        )
    Console(soft_wrap=True).print(table)
