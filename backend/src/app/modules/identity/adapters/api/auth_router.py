import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Path
from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.http.cross_site import (
    CrossSiteRequestError,
    refuse_cross_site,
)
from app.entrypoints.api.shared.http.parameters import SessionId
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.identity.adapters.api.cookies import (
    clear_session_cookies,
    session_cookie_header,
    set_session_cookies,
)
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_adopt_device_name_use_case,
    get_change_password_use_case,
    get_client_device,
    get_client_ip,
    get_current_session_id,
    get_device_token,
    get_get_setup_status_use_case,
    get_identity_actor,
    get_identity_settings_dep,
    get_list_device_name_suggestions_use_case,
    get_list_own_devices_use_case,
    get_list_own_sessions_use_case,
    get_rename_own_device_use_case,
    get_revoke_other_sessions_use_case,
    get_revoke_own_device_use_case,
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
    DEVICE_EXAMPLE,
    DEVICE_NAME_EXAMPLE,
    DEVICE_NAME_SUGGESTION_EXAMPLE,
    AuthStatusResponse,
    ChangePasswordRequest,
    DeviceNameResponse,
    DeviceNameSuggestionResponse,
    LoginRequest,
    OwnDeviceResponse,
    RenameDeviceRequest,
    RevokedSessionsResponse,
    SessionResponse,
    SetupRequest,
    SetupResponse,
    UpdateMeRequest,
    UserResponse,
)
from app.modules.identity.application.adopt_device_name import (
    AdoptDeviceName,
    AdoptDeviceNameCommand,
)
from app.modules.identity.application.change_password import ChangePassword
from app.modules.identity.application.client_device import ClientDevice
from app.modules.identity.application.get_setup_status import (
    GetSetupStatus,
    GetSetupStatusQuery,
)
from app.modules.identity.application.list_device_name_suggestions import (
    ListDeviceNameSuggestions,
    ListDeviceNameSuggestionsQuery,
)
from app.modules.identity.application.list_own_devices import (
    ListOwnDevices,
    ListOwnDevicesQuery,
)
from app.modules.identity.application.list_own_sessions import (
    ListOwnSessions,
    ListOwnSessionsQuery,
)
from app.modules.identity.application.rename_own_device import (
    RenameOwnDevice,
    RenameOwnDeviceCommand,
)
from app.modules.identity.application.revoke_other_sessions import (
    RevokeOtherSessions,
    RevokeOtherSessionsCommand,
)
from app.modules.identity.application.revoke_own_device import (
    RevokeOwnDevice,
    RevokeOwnDeviceCommand,
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
    DeviceNotFoundError,
    InvalidCredentialsError,
    InvalidDeviceNameError,
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
# The signed-in account's own details, password and devices.
me_router = APIRouter(
    prefix="/me", tags=["Authentication"], route_class=PermissionAwareRoute
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
        201: {"headers": session_cookie_header()},
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
    set_session_cookies(
        request, response, result.token, settings, device_token=result.device_token
    )
    return SetupResponse.from_result(result)


@public_router.post(
    "/login",
    response_model=UserResponse,
    operation_id="sign_in",
    dependencies=[Depends(refuse_cross_site)],
    responses={
        200: {"headers": session_cookie_header()},
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
    device_token: Annotated[str | None, Depends(get_device_token)],
) -> UserResponse:
    """Sign in, setting the session cookie and the device cookie.

    Refused with 403 `cross_site_refused` when a page on another site sent it.

    The 403 `account_disabled` answer is given only when the password was
    right; a wrong password for a disabled account gets the same 401 as any
    other. Failures are throttled per username and per client address (429 with
    `Retry-After`) whether or not the account exists. A browser sending a device
    cookie it was given when signing in to this account before is counted on its
    own, higher limit instead of the username's, so failures from elsewhere
    cannot lock it out.
    """
    logger.debug(
        "sign_in_device_headers",
        **device_header_fields(request.headers, client_ip),
    )
    result = await use_case.handle(
        payload.to_command(
            client_ip=client_ip, device=device, device_token=device_token
        ),
        ANONYMOUS_ACTOR,
    )
    set_session_cookies(
        request, response, result.token, settings, device_token=result.device_token
    )
    return UserResponse.from_domain(result.user)


@router.post(
    "/logout",
    status_code=204,
    operation_id="sign_out",
    responses={
        204: {
            "description": "Signed out.",
            "headers": {
                **session_cookie_header(clears=True),
                "Clear-Site-Data": {
                    "description": (
                        "Clears the browser HTTP cache when a session was ended."
                    ),
                    "schema": {"type": "string", "examples": ['"cache"']},
                },
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
    """Sign out, ending the session and clearing its cookie.

    The device cookie is kept: signing out does not forget the browser.
    Without a session cookie nothing is changed: the same-origin check does not
    apply then, so clearing cookies would let a cross-site POST log someone out.
    """
    if token is None:
        return
    await use_case.handle(SignOutCommand(token=token), ANONYMOUS_ACTOR)
    clear_session_cookies(request, response, settings)
    response.headers["Clear-Site-Data"] = '"cache"'


@me_router.get(
    "",
    response_model=UserResponse,
    operation_id="get_current_user",
    responses=_UNAUTHENTICATED,
)
async def get_current_user(
    user: Annotated[User, Depends(get_signed_in_user)],
) -> UserResponse:
    """Return the signed-in account."""
    return UserResponse.from_domain(user)


@me_router.patch(
    "",
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


@me_router.post(
    "/password",
    response_model=UserResponse,
    operation_id="change_password",
    responses={
        200: {"headers": session_cookie_header()},
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

    Every remembered browser is forgotten, and this one gets a new device cookie.
    Wrong current passwords are throttled per user and per client address.
    """
    result = await use_case.handle(
        payload.to_command(client_ip=client_ip, device=device), actor
    )
    set_session_cookies(
        request, response, result.token, settings, device_token=result.device_token
    )
    return UserResponse.from_domain(result.user)


@me_router.get(
    "/devices",
    response_model=list[OwnDeviceResponse],
    operation_id="list_own_devices",
    tags=["Sessions"],
    responses={
        200: {"content": {"application/json": {"example": [DEVICE_EXAMPLE]}}},
        **_UNAUTHENTICATED,
    },
)
async def list_own_devices(
    use_case: Annotated[ListOwnDevices, Depends(get_list_own_devices_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    current_session_id: Annotated[uuid.UUID, Depends(get_current_session_id)],
) -> list[OwnDeviceResponse]:
    """List the browsers you are signed in on, each with its active sessions."""
    devices = await use_case.handle(
        ListOwnDevicesQuery(current_session_id=current_session_id), actor
    )
    return [OwnDeviceResponse.from_own_device(d) for d in devices]


@me_router.delete(
    "/devices/{device_id}",
    response_model=RevokedSessionsResponse,
    operation_id="revoke_own_device",
    tags=["Sessions"],
    responses={
        200: {"content": {"application/json": {"example": {"ended": 1}}}},
        **_UNAUTHENTICATED,
        **error_response(DeviceNotFoundError, detail="That device was not found."),
        **error_response(
            CurrentSessionError, detail="Cannot revoke the current device."
        ),
    },
)
async def revoke_own_device(
    device_id: Annotated[
        uuid.UUID, Path(description="The device to sign out and forget.")
    ],
    use_case: Annotated[RevokeOwnDevice, Depends(get_revoke_own_device_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    current_session_id: Annotated[uuid.UUID, Depends(get_current_session_id)],
) -> RevokedSessionsResponse:
    """Sign out one of your devices and forget it, ending all its sessions."""
    ended = await use_case.handle(
        RevokeOwnDeviceCommand(
            device_id=device_id, current_session_id=current_session_id
        ),
        actor,
    )
    return RevokedSessionsResponse(ended=ended)


@me_router.patch(
    "/devices/{device_id}",
    response_model=DeviceNameResponse,
    operation_id="rename_own_device",
    tags=["Sessions"],
    responses={
        200: {"content": {"application/json": {"example": DEVICE_NAME_EXAMPLE}}},
        **_UNAUTHENTICATED,
        **error_response(DeviceNotFoundError, detail="That device was not found."),
        **error_response(
            InvalidDeviceNameError, detail="A device name can be at most 60 characters."
        ),
    },
)
async def rename_own_device(
    device_id: Annotated[uuid.UUID, Path(description="The device to name.")],
    payload: RenameDeviceRequest,
    use_case: Annotated[RenameOwnDevice, Depends(get_rename_own_device_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> DeviceNameResponse:
    """Name one of your devices, or clear its name with a blank one."""
    device = await use_case.handle(
        RenameOwnDeviceCommand(device_id=device_id, name=payload.name), actor
    )
    return DeviceNameResponse.from_domain(device)


@me_router.get(
    "/devices/suggestions",
    response_model=list[DeviceNameSuggestionResponse],
    operation_id="list_device_name_suggestions",
    tags=["Sessions"],
    responses={
        200: {
            "content": {
                "application/json": {"example": [DEVICE_NAME_SUGGESTION_EXAMPLE]}
            }
        },
        **_UNAUTHENTICATED,
    },
)
async def list_device_name_suggestions(
    use_case: Annotated[
        ListDeviceNameSuggestions, Depends(get_list_device_name_suggestions_use_case)
    ],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    current_session_id: Annotated[uuid.UUID, Depends(get_current_session_id)],
) -> list[DeviceNameSuggestionResponse]:
    """List older devices of yours whose name this browser could take.

    Only unused devices of the same browser, platform and mobile flag are
    listed, and only while this browser has no name of its own.
    """
    devices = await use_case.handle(
        ListDeviceNameSuggestionsQuery(current_session_id=current_session_id), actor
    )
    return [DeviceNameSuggestionResponse.from_domain(d) for d in devices]


@me_router.post(
    "/devices/{device_id}/adopt",
    response_model=DeviceNameResponse,
    operation_id="adopt_device_name",
    tags=["Sessions"],
    responses={
        200: {"content": {"application/json": {"example": DEVICE_NAME_EXAMPLE}}},
        **_UNAUTHENTICATED,
        **error_response(
            DeviceNotFoundError, detail="That device's name cannot be reused."
        ),
    },
)
async def adopt_device_name(
    device_id: Annotated[
        uuid.UUID, Path(description="The older device whose name to take.")
    ],
    use_case: Annotated[AdoptDeviceName, Depends(get_adopt_device_name_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    current_session_id: Annotated[uuid.UUID, Depends(get_current_session_id)],
) -> DeviceNameResponse:
    """Take an older device's name for this browser and forget that device.

    The older device is signed out. Only a device listed by
    `GET /me/devices/suggestions` can be taken.
    """
    device = await use_case.handle(
        AdoptDeviceNameCommand(
            current_session_id=current_session_id, from_device_id=device_id
        ),
        actor,
    )
    return DeviceNameResponse.from_domain(device)


@me_router.get(
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


@me_router.delete(
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
    session_id: SessionId,
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


@me_router.delete(
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
    """Sign out everywhere except this device, forgetting the other devices."""
    ended = await use_case.handle(
        RevokeOtherSessionsCommand(current_session_id=current_session_id),
        actor,
    )
    return RevokedSessionsResponse(ended=ended)
