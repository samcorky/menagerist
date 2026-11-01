from typing import Annotated

import structlog
from fastapi import Depends
from starlette.requests import Request

from app.entrypoints.api.shared.authorisation import get_role_authorisation
from app.entrypoints.api.shared.http.bearer import bearer_token
from app.modules.identity.adapters.api.dependencies import (
    bind_session_context,
    get_authenticate_api_token_use_case,
    get_get_current_user_use_case,
    get_get_setup_status_use_case,
    get_session_token,
)
from app.modules.identity.application.authenticate_api_token import (
    AuthenticateApiToken,
    AuthenticateApiTokenCommand,
)
from app.modules.identity.application.get_current_user import (
    GetCurrentUser,
    GetCurrentUserQuery,
)
from app.modules.identity.application.get_setup_status import (
    GetSetupStatus,
    GetSetupStatusQuery,
)
from app.modules.identity.domain.errors import (
    InvalidApiTokenError,
    PasswordExpiredError,
    SessionRequiredError,
    SetupRequiredError,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor


async def _token_actor(
    request: Request, value: str, authenticate: AuthenticateApiToken
) -> Actor:
    """Resolve a bearer token to its owner, carrying the token's grants."""
    resolved = await authenticate.handle(
        AuthenticateApiTokenCommand(value=value), ANONYMOUS_ACTOR
    )
    if resolved is None:
        raise InvalidApiTokenError("The access token is not valid.")
    user = resolved.user
    token_id = str(resolved.token_id)
    structlog.contextvars.bind_contextvars(user_id=str(user.id), token_id=token_id)
    # Read back by the access-log line, which is written outside the endpoint task.
    request.state.user_id = str(user.id)
    request.state.token_id = token_id
    if user.password_expired:
        raise PasswordExpiredError("Change your password to continue.")
    return Actor(id=user.id, roles=frozenset({user.role.value}), grants=resolved.grants)


async def get_current_actor(
    request: Request,
    token: Annotated[str | None, Depends(get_session_token)],
    current_user: Annotated[GetCurrentUser, Depends(get_get_current_user_use_case)],
    setup_status: Annotated[GetSetupStatus, Depends(get_get_setup_status_use_case)],
    authenticate: Annotated[
        AuthenticateApiToken, Depends(get_authenticate_api_token_use_case)
    ],
) -> Actor:
    """Resolve a bearer token or the session cookie to the actor for a request.

    A bearer header is authoritative: it is never combined with, or replaced by,
    the cookie.

    Raises:
        InvalidApiTokenError: If a bearer token is malformed, unknown, expired or
            its owner is disabled.
        SetupRequiredError: If no account exists yet.
        SessionRequiredError: If there is no live session for an enabled user.
        PasswordExpiredError: If the account's password has expired.
    """
    bearer = bearer_token(request)
    if bearer is not None:
        return await _token_actor(request, bearer, authenticate)
    resolved = (
        None
        if token is None
        else await current_user.handle(
            GetCurrentUserQuery(token=token), ANONYMOUS_ACTOR
        )
    )
    if resolved is None:
        if await setup_status.handle(GetSetupStatusQuery(), ANONYMOUS_ACTOR):
            raise SetupRequiredError("Create the first account to continue.")
        raise SessionRequiredError("Sign in to continue.")
    bind_session_context(request, resolved)
    user = resolved.user
    if user.password_expired:
        raise PasswordExpiredError("Change your password to continue.")
    return Actor(id=user.id, roles=frozenset({user.role.value}))


__all__ = [
    "get_current_actor",
    "get_role_authorisation",
]
