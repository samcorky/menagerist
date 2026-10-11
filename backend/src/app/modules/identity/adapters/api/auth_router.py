from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.identity.adapters.api.cookies import (
    clear_session_cookies,
    set_session_cookies,
)
from app.modules.identity.adapters.api.dependencies import (
    get_change_password_use_case,
    get_get_setup_status_use_case,
    get_identity_actor,
    get_identity_settings_dep,
    get_session_token,
    get_setup_first_admin_use_case,
    get_sign_in_use_case,
    get_sign_out_use_case,
    get_signed_in_user,
)
from app.modules.identity.adapters.api.schemas import (
    AuthStatusResponse,
    ChangePasswordRequest,
    LoginRequest,
    SetupRequest,
    SetupResponse,
    UserResponse,
)
from app.modules.identity.application.change_password import ChangePassword
from app.modules.identity.application.get_setup_status import (
    GetSetupStatus,
    GetSetupStatusQuery,
)
from app.modules.identity.application.setup_first_admin import SetupFirstAdmin
from app.modules.identity.application.sign_in import SignIn
from app.modules.identity.application.sign_out import SignOut, SignOutCommand
from app.modules.identity.domain.errors import (
    CurrentPasswordIncorrectError,
    InvalidCredentialsError,
    InvalidPasswordError,
    SessionRequiredError,
    SetupAlreadyDoneError,
    SignInThrottledError,
)
from app.modules.identity.domain.user import User
from app.platform.config import IdentitySettings
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor

# Open to callers with no session or CSRF token (sign-in and first-run setup).
public_router = APIRouter(
    prefix="/auth", tags=["Authentication"], route_class=PermissionAwareRoute
)
# Needs the CSRF check like the rest of the API.
router = APIRouter(
    prefix="/auth", tags=["Authentication"], route_class=PermissionAwareRoute
)

_UNAUTHENTICATED = error_response(SessionRequiredError, detail="Sign in to continue.")


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
    responses={
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
) -> SetupResponse:
    """Create the first administrator and sign them in. Only works once."""
    result = await use_case.handle(payload.to_command(), ANONYMOUS_ACTOR)
    set_session_cookies(request, response, result.token, settings)
    return SetupResponse.from_result(result)


@public_router.post(
    "/login",
    response_model=UserResponse,
    operation_id="sign_in",
    responses={
        **error_response(
            InvalidCredentialsError, detail="Incorrect username or password."
        ),
        **error_response(
            SignInThrottledError, detail="Too many failed attempts. Try again later."
        ),
    },
)
async def sign_in(
    payload: LoginRequest,
    request: Request,
    response: Response,
    use_case: Annotated[SignIn, Depends(get_sign_in_use_case)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
) -> UserResponse:
    """Sign in, setting the session and CSRF cookies."""
    result = await use_case.handle(payload.to_command(), ANONYMOUS_ACTOR)
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

    Without a session cookie nothing is changed: CSRF is not checked then, so
    clearing cookies would let a cross-site POST log someone out.
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


@router.post(
    "/password",
    response_model=UserResponse,
    operation_id="change_password",
    responses={
        **_UNAUTHENTICATED,
        **error_response(
            CurrentPasswordIncorrectError, detail="The current password is incorrect."
        ),
    },
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    use_case: Annotated[ChangePassword, Depends(get_change_password_use_case)],
    actor: Annotated[Actor, Depends(get_identity_actor)],
    settings: Annotated[IdentitySettings, Depends(get_identity_settings_dep)],
) -> UserResponse:
    """Change your password. Other sessions end and this one gets a new token."""
    result = await use_case.handle(payload.to_command(), actor)
    set_session_cookies(request, response, result.token, settings)
    return UserResponse.from_domain(result.user)
