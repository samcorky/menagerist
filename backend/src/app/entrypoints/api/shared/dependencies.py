from typing import Annotated

from fastapi import Depends
from starlette.requests import Request

from app.entrypoints.api.shared.authorisation import (
    get_authorisation_port,
    get_role_authorisation,
)
from app.modules.identity.adapters.api.dependencies import (
    bind_session_context,
    get_get_current_user_use_case,
    get_get_setup_status_use_case,
    get_session_token,
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
    PasswordExpiredError,
    SessionRequiredError,
    SetupRequiredError,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor


async def get_current_actor(
    request: Request,
    token: Annotated[str | None, Depends(get_session_token)],
    current_user: Annotated[GetCurrentUser, Depends(get_get_current_user_use_case)],
    setup_status: Annotated[GetSetupStatus, Depends(get_get_setup_status_use_case)],
) -> Actor:
    """Resolve the session cookie to the actor driving a content request.

    Raises:
        SetupRequiredError: If no account exists yet.
        SessionRequiredError: If there is no live session for an enabled user.
        PasswordExpiredError: If the account's password has expired.
    """
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
    "get_authorisation_port",
    "get_current_actor",
    "get_role_authorisation",
]
