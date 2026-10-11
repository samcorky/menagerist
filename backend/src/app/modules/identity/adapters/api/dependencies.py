import secrets
from datetime import timedelta
from functools import cache
from typing import TYPE_CHECKING, Annotated

import structlog
from fastapi import Depends
from starlette.requests import Request

from app.modules.identity.adapters.claim.unwired_existing_data_claim import (
    UnwiredExistingDataClaim,
)
from app.modules.identity.adapters.persistence.unit_of_work import (
    build_identity_repos,
    create_identity_uow,
    create_identity_uow_on_session,
)
from app.modules.identity.adapters.security.password_authenticator import (
    PasswordAuthenticator,
)
from app.modules.identity.adapters.security.password_hasher_registry import (
    PasswordHasherRegistry,
)
from app.modules.identity.adapters.security.scrypt_password_hasher import (
    SCHEME as SCRYPT_SCHEME,
    ScryptPasswordHasher,
)
from app.modules.identity.adapters.security.session_token_generator import (
    SecretsSessionTokenGenerator,
)
from app.modules.identity.application.change_password import ChangePassword
from app.modules.identity.application.create_user import CreateUser
from app.modules.identity.application.get_current_user import (
    GetCurrentUser,
    GetCurrentUserQuery,
    ResolvedSession,
)
from app.modules.identity.application.get_setup_status import GetSetupStatus
from app.modules.identity.application.list_users import ListUsers
from app.modules.identity.application.reset_password import ResetPassword
from app.modules.identity.application.setup_first_admin import SetupFirstAdmin
from app.modules.identity.application.sign_in import SignIn
from app.modules.identity.application.sign_out import SignOut
from app.modules.identity.application.update_user import UpdateUser
from app.modules.identity.domain.errors import (
    PasswordExpiredError,
    SessionRequiredError,
)
from app.modules.identity.domain.user import User
from app.modules.identity.ports.existing_data_claim import ExistingDataClaim
from app.modules.identity.ports.password_hasher import PasswordHasher
from app.modules.identity.ports.session_token_generator import SessionTokenGenerator
from app.modules.identity.ports.unit_of_work import IdentityRepos, IdentityUnitOfWork
from app.platform.config import IdentitySettings, get_identity_settings
from app.platform.database import get_session_factory
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@cache
def _hasher() -> PasswordHasher:
    return PasswordHasherRegistry(
        {SCRYPT_SCHEME: ScryptPasswordHasher()},
        default=get_identity_settings().password_hasher,
    )


@cache
def _decoy_hash() -> str:
    """A hash made once per process, verified against for unknown usernames."""
    return _hasher().hash(secrets.token_urlsafe(16))


def get_identity_settings_dep() -> IdentitySettings:
    """Return the cached identity settings."""
    return get_identity_settings()


def get_password_hasher() -> PasswordHasher:
    """Return the process-wide password hasher registry."""
    return _hasher()


def get_decoy_hash() -> str:
    """Return the process-wide decoy hash."""
    return _decoy_hash()


def get_session_token_generator() -> SessionTokenGenerator:
    """Return the session token generator."""
    return SecretsSessionTokenGenerator()


def get_existing_data_claim() -> ExistingDataClaim:
    """Return the claim port; fails closed until the entrypoint wires the real one."""
    return UnwiredExistingDataClaim()


def get_session_ttl(
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
) -> timedelta:
    """Return how long a new session lives."""
    return timedelta(hours=settings.session_ttl_hours)


def get_identity_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> IdentityUnitOfWork:
    """Return a unit of work over the identity tables, for commands."""
    return create_identity_uow(session_factory)


async def get_identity_repos(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[IdentityRepos]:
    """Return a read-only repository bundle over the identity tables."""
    async with session_factory() as session:
        yield build_identity_repos(session)


async def get_setup_session(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[AsyncSession]:
    """Yield the one session first-run setup and the data claim share."""
    async with session_factory() as session:
        yield session


def get_setup_identity_uow(
    session: Annotated[AsyncSession, Depends(get_setup_session)],
) -> IdentityUnitOfWork:
    """Return a unit of work on the shared setup session; setup commits once."""
    return create_identity_uow_on_session(session)


def get_authenticator(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    decoy_hash: Annotated[str, Depends(get_decoy_hash)],
) -> PasswordAuthenticator:
    return PasswordAuthenticator(uow, hasher, decoy_hash=decoy_hash)


def get_setup_first_admin_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_setup_identity_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
    claim: Annotated[ExistingDataClaim, Depends(get_existing_data_claim)],
    ttl: Annotated[timedelta, Depends(get_session_ttl)],
) -> SetupFirstAdmin:
    return SetupFirstAdmin(uow, hasher, tokens, claim, session_ttl=ttl)


def get_sign_in_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    authenticator: Annotated[PasswordAuthenticator, Depends(get_authenticator)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
    ttl: Annotated[timedelta, Depends(get_session_ttl)],
) -> SignIn:
    return SignIn(uow, authenticator, tokens, session_ttl=ttl)


def get_sign_out_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
) -> SignOut:
    return SignOut(uow, tokens)


def get_get_current_user_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
) -> GetCurrentUser:
    return GetCurrentUser(uow, tokens)


def get_get_setup_status_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
) -> GetSetupStatus:
    return GetSetupStatus(repos)


def get_change_password_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
    ttl: Annotated[timedelta, Depends(get_session_ttl)],
) -> ChangePassword:
    return ChangePassword(uow, hasher, tokens, session_ttl=ttl)


def get_create_user_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> CreateUser:
    return CreateUser(uow, hasher)


def get_list_users_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
) -> ListUsers:
    return ListUsers(repos)


def get_update_user_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
) -> UpdateUser:
    return UpdateUser(uow)


def get_reset_password_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> ResetPassword:
    return ResetPassword(uow, hasher)


def get_session_token(
    request: Request,
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
) -> str | None:
    """Return the session token sent as a cookie, if any."""
    return request.cookies.get(settings.cookie_name)


def bind_session_context(request: Request, resolved: ResolvedSession) -> None:
    """Add `user_id` and `session_id` to the log context for the rest of the request.

    Dependencies and the endpoint share a task, and the request's task context is
    discarded with the request, so nothing carries over to another request. Only
    the session's row id is bound, never its token.
    """
    user_id, session_id = str(resolved.user.id), str(resolved.session_id)
    structlog.contextvars.bind_contextvars(user_id=user_id, session_id=session_id)
    # Read back by the access-log line, which is written outside the endpoint task.
    request.state.user_id = user_id
    request.state.session_id = session_id


async def get_signed_in_user(
    request: Request,
    token: Annotated[str | None, Depends(get_session_token)],
    use_case: Annotated[GetCurrentUser, Depends(get_get_current_user_use_case)],
) -> User:
    """Resolve the session cookie to its user.

    Raises:
        SessionRequiredError: If there is no live session.
    """
    resolved = (
        None
        if token is None
        else await use_case.handle(GetCurrentUserQuery(token=token), ANONYMOUS_ACTOR)
    )
    if resolved is None:
        raise SessionRequiredError("Sign in to continue.")
    bind_session_context(request, resolved)
    return resolved.user


def get_identity_actor(
    user: Annotated[User, Depends(get_signed_in_user)],
) -> Actor:
    """Return the signed-in user as the actor driving this request."""
    return Actor(id=user.id, roles=frozenset({user.role.value}))


def get_active_identity_actor(
    user: Annotated[User, Depends(get_signed_in_user)],
) -> Actor:
    """Like `get_identity_actor`, but refuses an account whose password expired.

    Raises:
        PasswordExpiredError: If the password must be changed first.
    """
    if user.password_expired:
        raise PasswordExpiredError("Change your password to continue.")
    return Actor(id=user.id, roles=frozenset({user.role.value}))
