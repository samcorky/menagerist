import secrets
import uuid
from datetime import timedelta
from functools import cache
from typing import TYPE_CHECKING, Annotated

import structlog
from fastapi import Depends
from starlette.requests import Request

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.authorisation import (
    TOKEN_GRANTABLE_PERMISSIONS,
    get_authorisation_port,
)
from app.entrypoints.api.shared.http.bearer import bearer_token
from app.modules.identity.adapters.api.cookies import (
    session_cookie_name,
    session_cookie_value,
)
from app.modules.identity.adapters.claim.unwired_existing_data_claim import (
    UnwiredExistingDataClaim,
)
from app.modules.identity.adapters.persistence.unit_of_work import (
    build_identity_repos,
    create_identity_uow,
    create_identity_uow_on_session,
)
from app.modules.identity.adapters.security.bounded_password_hasher import (
    BoundedPasswordHasher,
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
from app.modules.identity.adapters.security.secrets_api_token_generator import (
    SecretsApiTokenGenerator,
)
from app.modules.identity.adapters.security.session_token_generator import (
    SecretsSessionTokenGenerator,
)
from app.modules.identity.application.authenticate_api_token import AuthenticateApiToken
from app.modules.identity.application.change_password import ChangePassword
from app.modules.identity.application.client_device import ClientDevice
from app.modules.identity.application.create_api_token import CreateApiToken
from app.modules.identity.application.create_user import CreateUser
from app.modules.identity.application.get_current_user import (
    GetCurrentUser,
    GetCurrentUserQuery,
    ResolvedSession,
)
from app.modules.identity.application.get_setup_status import GetSetupStatus
from app.modules.identity.application.has_administrator import HasAdministrator
from app.modules.identity.application.list_grantable_permissions import (
    ListGrantablePermissions,
)
from app.modules.identity.application.list_own_api_tokens import ListOwnApiTokens
from app.modules.identity.application.list_own_sessions import ListOwnSessions
from app.modules.identity.application.list_sessions import ListSessions
from app.modules.identity.application.list_users import ListUsers
from app.modules.identity.application.reset_password import ResetPassword
from app.modules.identity.application.revoke_other_sessions import RevokeOtherSessions
from app.modules.identity.application.revoke_own_api_token import RevokeOwnApiToken
from app.modules.identity.application.revoke_own_session import RevokeOwnSession
from app.modules.identity.application.revoke_session import RevokeSession
from app.modules.identity.application.rotate_api_token import RotateApiToken
from app.modules.identity.application.set_own_display_name import SetOwnDisplayName
from app.modules.identity.application.setup_first_admin import SetupFirstAdmin
from app.modules.identity.application.sign_in import SignIn
from app.modules.identity.application.sign_in_throttle import SignInThrottle
from app.modules.identity.application.sign_out import SignOut
from app.modules.identity.application.unlock_user import UnlockUser
from app.modules.identity.application.update_user import UpdateUser
from app.modules.identity.domain.errors import (
    PasswordExpiredError,
    SessionRequiredError,
)
from app.modules.identity.domain.throttle import ThrottlePolicy
from app.modules.identity.domain.user import User
from app.modules.identity.ports.api_token_generator import ApiTokenGenerator
from app.modules.identity.ports.existing_data_claim import ExistingDataClaim
from app.modules.identity.ports.password_hasher import PasswordHasher
from app.modules.identity.ports.session_token_generator import SessionTokenGenerator
from app.modules.identity.ports.unit_of_work import IdentityRepos, IdentityUnitOfWork
from app.platform.config import IdentitySettings, get_identity_settings
from app.platform.database import get_session_factory
from app.shared_kernel.access_guard import AccessGuard
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@cache
def _hasher() -> PasswordHasher:
    settings = get_identity_settings()
    return BoundedPasswordHasher(
        PasswordHasherRegistry(
            {SCRYPT_SCHEME: ScryptPasswordHasher()}, default=settings.password_hasher
        ),
        concurrency=settings.password_hash_concurrency,
    )


@cache
def _decoy_hash() -> str:
    """A hash made once per process, verified against for unknown usernames."""
    return _hasher().hash(secrets.token_urlsafe(16))


def _grantable() -> frozenset[str]:
    """The permission strings a token may be given."""
    return frozenset(p.value for p in TOKEN_GRANTABLE_PERMISSIONS)


def get_identity_settings_dep() -> IdentitySettings:
    """Return the cached identity settings."""
    return get_identity_settings()


def get_password_hasher() -> PasswordHasher:
    """Return the process-wide password hasher registry."""
    return _hasher()


def get_decoy_hash() -> str:
    """Return the process-wide decoy hash."""
    return _decoy_hash()


def get_sign_in_throttle(
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
) -> SignInThrottle:
    """Return the failed-attempt limits configured for this process."""
    return SignInThrottle(
        ThrottlePolicy(
            username_limit=settings.sign_in_username_attempts,
            ip_limit=settings.sign_in_ip_attempts,
            window=timedelta(minutes=settings.sign_in_window_minutes),
        )
    )


def get_client_ip(request: Request) -> str | None:
    """Return the client address as the server sees it.

    The ASGI wrapper in `entrypoints/api/__init__.py` has already applied
    X-Forwarded-For from `MENAGERIST_API_TRUSTED_PROXIES` peers only, so this is
    `request.client.host`.
    """
    return None if request.client is None else request.client.host


def get_client_device(request: Request) -> ClientDevice:
    """Extract client device hints and user agent from request headers."""
    ua_raw = request.headers.get("User-Agent")
    user_agent = ua_raw.strip() if ua_raw is not None and ua_raw.strip() else None

    platform_raw = request.headers.get("Sec-CH-UA-Platform")
    platform: str | None = None
    if platform_raw is not None:
        cleaned_platform = platform_raw.strip().strip('"').strip()
        platform = cleaned_platform if cleaned_platform else None

    mobile_raw = request.headers.get("Sec-CH-UA-Mobile")
    mobile: bool | None = None
    if mobile_raw is not None:
        val = mobile_raw.strip()
        if val == "?1":
            mobile = True
        elif val == "?0":
            mobile = False

    return ClientDevice(user_agent=user_agent, platform=platform, mobile=mobile)


def get_session_token_generator() -> SessionTokenGenerator:
    """Return the session token generator."""
    return SecretsSessionTokenGenerator()


def get_api_token_generator() -> ApiTokenGenerator:
    """Return the personal access token generator."""
    return SecretsApiTokenGenerator()


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
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> SetupFirstAdmin:
    return SetupFirstAdmin(uow, guard, hasher, tokens, claim, session_ttl=ttl)


def get_sign_in_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    authenticator: Annotated[PasswordAuthenticator, Depends(get_authenticator)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    throttle: Annotated[SignInThrottle, Depends(get_sign_in_throttle)],
    decoy_hash: Annotated[str, Depends(get_decoy_hash)],
    ttl: Annotated[timedelta, Depends(get_session_ttl)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> SignIn:
    return SignIn(
        uow,
        guard,
        authenticator,
        tokens,
        hasher,
        throttle,
        decoy_hash=decoy_hash,
        session_ttl=ttl,
    )


def get_sign_out_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> SignOut:
    return SignOut(uow, guard, tokens)


def get_get_current_user_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetCurrentUser:
    idle = settings.session_idle_hours
    return GetCurrentUser(
        uow, guard, tokens, idle_timeout=timedelta(hours=idle) if idle else None
    )


def get_authenticate_api_token_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    tokens: Annotated[ApiTokenGenerator, Depends(get_api_token_generator)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> AuthenticateApiToken:
    return AuthenticateApiToken(uow, guard, tokens)


def get_create_api_token_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[ApiTokenGenerator, Depends(get_api_token_generator)],
    throttle: Annotated[SignInThrottle, Depends(get_sign_in_throttle)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CreateApiToken:
    return CreateApiToken(
        uow,
        guard,
        hasher,
        tokens,
        throttle,
        get_authorisation_port(),
        grantable=_grantable(),
        default_days=settings.api_token_default_days,
        max_days=settings.api_token_max_days,
        max_tokens=settings.api_tokens_per_user,
    )


def get_rotate_api_token_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[ApiTokenGenerator, Depends(get_api_token_generator)],
    throttle: Annotated[SignInThrottle, Depends(get_sign_in_throttle)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RotateApiToken:
    return RotateApiToken(
        uow,
        guard,
        hasher,
        tokens,
        throttle,
        get_authorisation_port(),
        default_days=settings.api_token_default_days,
        max_days=settings.api_token_max_days,
    )


def get_list_own_api_tokens_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListOwnApiTokens:
    return ListOwnApiTokens(repos, guard)


def get_revoke_own_api_token_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RevokeOwnApiToken:
    return RevokeOwnApiToken(uow, guard)


def get_list_grantable_permissions_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListGrantablePermissions:
    return ListGrantablePermissions(
        repos, guard, get_authorisation_port(), grantable=_grantable()
    )


def get_get_setup_status_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetSetupStatus:
    return GetSetupStatus(repos, guard)


def get_change_password_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[SessionTokenGenerator, Depends(get_session_token_generator)],
    throttle: Annotated[SignInThrottle, Depends(get_sign_in_throttle)],
    ttl: Annotated[timedelta, Depends(get_session_ttl)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ChangePassword:
    return ChangePassword(uow, guard, hasher, tokens, throttle, session_ttl=ttl)


def get_set_own_display_name_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> SetOwnDisplayName:
    return SetOwnDisplayName(uow, guard)


def get_create_user_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> CreateUser:
    return CreateUser(uow, guard, hasher)


def get_list_users_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListUsers:
    return ListUsers(repos, guard)


def get_update_user_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> UpdateUser:
    return UpdateUser(uow, guard)


def get_reset_password_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> ResetPassword:
    return ResetPassword(uow, guard, hasher)


def get_unlock_user_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> UnlockUser:
    return UnlockUser(uow, guard)


def get_has_administrator_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> HasAdministrator:
    return HasAdministrator(repos, guard)


def get_list_own_sessions_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListOwnSessions:
    idle = settings.session_idle_hours
    return ListOwnSessions(
        repos, guard, idle_timeout=timedelta(hours=idle) if idle else None
    )


def get_revoke_own_session_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RevokeOwnSession:
    return RevokeOwnSession(uow, guard)


def get_revoke_other_sessions_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RevokeOtherSessions:
    return RevokeOtherSessions(uow, guard)


def get_list_sessions_use_case(
    repos: Annotated[IdentityRepos, Depends(get_identity_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
) -> ListSessions:
    idle = settings.session_idle_hours
    return ListSessions(
        repos, guard, idle_timeout=timedelta(hours=idle) if idle else None
    )


def get_revoke_session_use_case(
    uow: Annotated[IdentityUnitOfWork, Depends(get_identity_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RevokeSession:
    return RevokeSession(uow, guard)


def get_session_token(
    request: Request,
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
) -> str | None:
    """Return the session token sent as a cookie, if any.

    A bearer header beside it makes the request token-authenticated, so the cookie
    is not read at all and every cookie-only route refuses it.
    """
    if bearer_token(request) is not None:
        return None
    return session_cookie_value(request, session_cookie_name(request, settings))


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


def get_current_session_id(
    request: Request,
    _user: Annotated[User, Depends(get_signed_in_user)],
) -> uuid.UUID:
    """Return the current session ID bound to the request.

    Raises:
        SessionRequiredError: If there is no live session.
    """
    session_id: str | uuid.UUID | None = getattr(request.state, "session_id", None)
    if session_id is None:
        raise SessionRequiredError("Sign in to continue.")
    return session_id if isinstance(session_id, uuid.UUID) else uuid.UUID(session_id)
