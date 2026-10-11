import asyncio
import getpass
import os
import sys
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import TYPE_CHECKING, Any, NoReturn

import structlog
from cyclopts import App

from app.modules.identity.adapters.claim.unwired_existing_data_claim import (
    UnwiredExistingDataClaim,
)
from app.shared_kernel.errors import DomainError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.identity.ports.existing_data_claim import ExistingDataClaim
    from app.modules.identity.ports.password_hasher import PasswordHasher

logger = structlog.get_logger(__name__)

identity_app = App(name="identity", help="Manage accounts.")

PASSWORD_ENV_VAR = "MENAGERIST_INITIAL_PASSWORD"

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


def _read_password() -> str:
    """Read the password from the environment or a hidden, confirmed prompt."""
    from_env = os.environ.get(PASSWORD_ENV_VAR)
    if from_env:
        return from_env
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
                user = await CreateUser(uow, hasher).handle(
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
def reset_password(*, username: str) -> None:
    """Give an account a new initial password and end its sessions.

    Args:
        username: Username of the account to reset.
    """
    password = _read_password()

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
            await ResetPassword(uow, _hasher()).handle(
                ResetPasswordCommand(user_id=user.id, password=password),
                SYSTEM_ACTOR,
            )
            return (
                f"Password reset for '{user.username}'. "
                + "They must change it at next sign-in."
            )

    print(_run(_reset()))


@identity_app.command(name="list")
def list_accounts() -> None:
    """List every account: username, display name, role and disabled flag."""

    async def _list() -> list[str]:
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
            users = await ListUsers(build_identity_repos(session)).handle(
                ListUsersQuery(), SYSTEM_ACTOR
            )
        return [
            "\t".join(
                (
                    user.username,
                    user.display_name,
                    user.role.value,
                    "disabled" if user.disabled else "active",
                )
            )
            for user in users
        ]

    for line in _run(_list()):
        print(line)
