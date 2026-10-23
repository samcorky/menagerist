import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.http.cross_site import (
    CrossSiteRequestError,
    refuse_cross_site,
)
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.identity.adapters.api.cookies import (
    clear_session_cookies,
    set_session_cookies,
)
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_change_password_use_case,
    get_client_device,
    get_client_ip,
    get_current_session_id,
    get_get_setup_status_use_case,
    get_identity_actor,
    get_identity_settings_dep,
    get_list_own_sessions_use_case,
    get_revoke_other_sessions_use_case,
    get_revoke_own_session_use_case,
    get_session_token,
    get_set_own_display_name_use_case,
    get_setup_first_admin_use_case,
    get_sign_in_use_case,
    get_sign_out_use_case,
    get_signed_in_user,
)
from app.modules.identity.adapters.api.device_header_fields import device_header_fields
from app.modules.identity.adapters.api.schemas import (
    AuthStatusResponse,
    ChangePasswordRequest,
    LoginRequest,
    RevokedSessionsResponse,
    SessionResponse,
    SetupRequest,
    SetupResponse,
    UpdateMeRequest,
    UserResponse,
)
from app.modules.identity.application.change_password import ChangePassword
from app.modules.identity.application.client_device import ClientDevice
from app.modules.identity.application.get_setup_status import (
    GetSetupStatus,
    GetSetupStatusQuery,
)
from app.modules.identity.application.list_own_sessions import (
    ListOwnSessions,
    ListOwnSessionsQuery,
)
from app.modules.identity.application.revoke_other_sessions import (
    RevokeOtherSessions,
    RevokeOtherSessionsCommand,
)
from app.modules.identity.application.revoke_own_session import (
    RevokeOwnSession,
    RevokeOwnSessionCommand,
)
from app.modules.identity.application.set_own_display_name import SetOwnDisplayName
from app.modules.identity.application.setup_first_admin import SetupFirstAdmin
from app.modules.identity.application.sign_in import SignIn
from app.modules.identity.application.sign_out import SignOut, SignOutCommand
from app.modules.identity.domain.errors import (
    AccountDisabledError,
    CurrentPasswordIncorrectError,
    CurrentSessionError,
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidUserError,
    PasswordUnchangedError,
    SessionNotFoundError,
    SessionRequiredError,
    SetupAlreadyDoneError,
    SignInThrottledError,
)
from app.modules.identity.domain.user import User
from app.platform.config import IdentitySettings
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor

logger = structlog.get_logger(__name__)

# Open to callers with no session (sign-in and first-run setup).
public_router = APIRouter(
    prefix="/auth", tags=["Authentication"], route_class=PermissionAwareRoute
)
# Needs the same-origin check like the rest of the API.
router = APIRouter(
    prefix="/auth", tags=["Authentication"], route_class=PermissionAwareRoute
)

_CROSS_SITE = error_response(
    CrossSiteRequestError, detail="This request was sent from another site."
)

_LOGIN_403 = error_response(
    AccountDisabledError,
    detail="This account has been disabled. Ask an administrator.",
)
_LOGIN_403[403]["description"] += (
    " Also used for a request sent from another site"
    + f" (`{CrossSiteRequestError.__name__}`:"
    + ' "This request was sent from another site.").'
)

_UNAUTHENTICATED = error_response(SessionRequiredError, detail="Sign in to continue.")

_THROTTLED = error_response(
    SignInThrottledError,
    detail="Too many failed attempts. Try again later.",
    description="Too many failed attempts recently; wait for `Retry-After` seconds.",
)
_THROTTLED[429]["headers"] = {
    "Retry-After": {
        "description": "Seconds to wait before trying again.",
        "schema": {"type": "integer"},
    }
}


@public_router.get(
    "/status", response_model=AuthStatusResponse, operation_id="get_auth_status"
)
async def get_auth_status(
    use_case: Annotated[GetSetupStatus, Depends(get_get_setup_status_use_case)],
) -> AuthStatusResponse:
    """Say whether first-run setup is still to be done."""
    setup_required = await use_case.handle(GetSetupStatusQuery(), ANONYMOUS_ACTOR)
    return AuthStatusResponse(setup_required=setup_required)


@public_router.post(
    "/setup",
    response_model=SetupResponse,
    status_code=201,
    operation_id="setup_first_admin",
    dependencies=[Depends(refuse_cross_site)],
    responses={
        **_CROSS_SITE,
        **error_response(
            SetupAlreadyDoneError, detail="Setup has already been completed."
        ),
        **error_response(
            InvalidPasswordError, detail="A password must be 10 to 128 characters."
        ),
    },
)
async def setup_first_admin(
    payload: SetupRequest,
    request: Request,
    response: Response,
    use_case: Annotated[SetupFirstAdmin, Depends(get_setup_first_admin_use_case)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
    device: Annotated[ClientDevice, Depends(get_client_device)],
) -> SetupResponse:
    """Create the first administrator and sign them in. Only works once.

    Refused with 403 `cross_site_refused` when a page on another site sent it.
    """
    result = await use_case.handle(
        payload.to_command(client_ip=client_ip, device=device), ANONYMOUS_ACTOR
    )
    set_session_cookies(request, response, result.token, settings)
    return SetupResponse.from_result(result)


@public_router.post(
    "/login",
    response_model=UserResponse,
    operation_id="sign_in",
    dependencies=[Depends(refuse_cross_site)],
    responses={
        **error_response(
            InvalidCredentialsError, detail="Incorrect username or password."
        ),
        **_LOGIN_403,
        **_THROTTLED,
    },
)
async def sign_in(
    payload: LoginRequest,
    request: Request,
    response: Response,
    use_case: Annotated[SignIn, Depends(get_sign_in_use_case)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
    device: Annotated[ClientDevice, Depends(get_client_device)],
) -> UserResponse:
    """Sign in, setting the session cookie.

    Refused with 403 `cross_site_refused` when a page on another site sent it.

    The 403 `account_disabled` answer is given only when the password was
    right; a wrong password for a disabled account gets the same 401 as any
    other. Failures are throttled per username and per client address (429 with
    `Retry-After`) whether or not the account exists.
    """
    logger.debug(
        "sign_in_device_headers",
        **device_header_fields(request.headers, client_ip),
    )
    result = await use_case.handle(
        payload.to_command(client_ip=client_ip, device=device), ANONYMOUS_ACTOR
    )
    set_session_cookies(request, response, result.token, settings)
    return UserResponse.from_domain(result.user)


@router.post(
    "/logout",
    status_code=204,
    operation_id="sign_out",
    responses={
        204: {
            "description": "Signed out.",
            "headers": {
                "Clear-Site-Data": {
                    "description": (
                        "Clears the browser HTTP cache when a session was ended."
                    ),
                    "schema": {"type": "string", "examples": ['"cache"']},
                }
            },
        }
    },
)
async def sign_out(
    request: Request,
    response: Response,
    use_case: Annotated[SignOut, Depends(get_sign_out_use_case)],
    token: Annotated[str | None, Depends(get_session_token)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
) -> None:
    """Sign out, ending the session and clearing the cookies.

    Without a session cookie nothing is changed: the same-origin check does not
    apply then, so clearing cookies would let a cross-site POST log someone out.
    """
    if token is None:
        return
    await use_case.handle(SignOutCommand(token=token), ANONYMOUS_ACTOR)
    clear_session_cookies(request, response, settings)
    response.headers["Clear-Site-Data"] = '"cache"'


@router.get(
    "/me",
    response_model=UserResponse,
    operation_id="get_current_user",
    responses=_UNAUTHENTICATED,
)
async def get_current_user(
    user: Annotated[User, Depends(get_signed_in_user)],
) -> UserResponse:
    """Return the signed-in account."""
    return UserResponse.from_domain(user)


@router.patch(
    "/me",
    response_model=UserResponse,
    operation_id="update_current_user",
    responses={
        **_UNAUTHENTICATED,
        **error_response(
            InvalidUserError, detail="A display name must be 1 to 120 characters."
        ),
    },
)
async def update_current_user(
    payload: UpdateMeRequest,
    use_case: Annotated[SetOwnDisplayName, Depends(get_set_own_display_name_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> UserResponse:
    """Change your own display name."""
    user = await use_case.handle(payload.to_command(), actor)
    return UserResponse.from_domain(user)


_CHANGE_PASSWORD_400 = error_response(
    CurrentPasswordIncorrectError, detail="The current password is incorrect."
)
_CHANGE_PASSWORD_400[400]["description"] += (
    " Also used for a new password that breaks the rules"
    + " (`InvalidPasswordError`) or equals the current one"
    + f" (`{PasswordUnchangedError.__name__}`: "
    + '"The new password must differ from the current one.").'
)


@router.post(
    "/password",
    response_model=UserResponse,
    operation_id="change_password",
    responses={
        **_UNAUTHENTICATED,
        **_CHANGE_PASSWORD_400,
        **_THROTTLED,
    },
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    use_case: Annotated[ChangePassword, Depends(get_change_password_use_case)],
    actor: Annotated[Actor, Depends(get_identity_actor)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
    device: Annotated[ClientDevice, Depends(get_client_device)],
) -> UserResponse:
    """Change your password. Other sessions end and this one gets a new token.

    Wrong current passwords are throttled per user and per client address.
    """
    result = await use_case.handle(
        payload.to_command(client_ip=client_ip, device=device), actor
    )
    set_session_cookies(request, response, result.token, settings)
    return UserResponse.from_domain(result.user)


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    operation_id="list_own_sessions",
    tags=["Sessions"],
    responses=_UNAUTHENTICATED,
)
async def list_own_sessions(
    use_case: Annotated[ListOwnSessions, Depends(get_list_own_sessions_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    current_session_id: Annotated[uuid.UUID, Depends(get_current_session_id)],
) -> list[SessionResponse]:
    """List all active devices for the current user."""
    sessions = await use_case.handle(
        ListOwnSessionsQuery(current_session_id=current_session_id),
        actor,
    )
    return [SessionResponse.from_own_session(s) for s in sessions]


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    operation_id="revoke_own_session",
    tags=["Sessions"],
    responses={
        **_UNAUTHENTICATED,
        **error_response(SessionNotFoundError, detail="That device was not found."),
        **error_response(
            CurrentSessionError, detail="Cannot revoke the current device."
        ),
    },
)
async def revoke_own_session(
    session_id: uuid.UUID,
    use_case: Annotated[RevokeOwnSession, Depends(get_revoke_own_session_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    current_session_id: Annotated[uuid.UUID, Depends(get_current_session_id)],
) -> None:
    """Sign out one of your active devices."""
    await use_case.handle(
        RevokeOwnSessionCommand(
            session_id=session_id, current_session_id=current_session_id
        ),
        actor,
    )


@router.delete(
    "/sessions",
    response_model=RevokedSessionsResponse,
    operation_id="revoke_other_sessions",
    tags=["Sessions"],
    responses=_UNAUTHENTICATED,
)
async def revoke_other_sessions(
    use_case: Annotated[
        RevokeOtherSessions, Depends(get_revoke_other_sessions_use_case)
    ],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    current_session_id: Annotated[uuid.UUID, Depends(get_current_session_id)],
) -> RevokedSessionsResponse:
    """Sign out all other active devices for your account."""
    ended = await use_case.handle(
        RevokeOtherSessionsCommand(current_session_id=current_session_id),
        actor,
    )
    return RevokedSessionsResponse(ended=ended)
