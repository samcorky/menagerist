import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_create_user_use_case,
    get_list_users_use_case,
    get_reset_password_use_case,
    get_update_user_use_case,
)
from app.modules.identity.adapters.api.schemas import (
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserResponse,
)
from app.modules.identity.application.create_user import CreateUser
from app.modules.identity.application.list_users import ListUsers, ListUsersQuery
from app.modules.identity.application.reset_password import ResetPassword
from app.modules.identity.application.update_user import UpdateUser
from app.modules.identity.domain.errors import (
    InvalidPasswordError,
    LastAdministratorError,
    SessionRequiredError,
    UsernameTakenError,
    UserNotFoundError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

router = APIRouter(prefix="/user", tags=["Users"], route_class=PermissionAwareRoute)

_ADMIN_ONLY = {
    **error_response(SessionRequiredError, detail="Sign in to continue."),
    **error_response(ForbiddenError, detail="Administrator access is required."),
}
_NOT_FOUND = error_response(UserNotFoundError, detail="That account does not exist.")


@router.get(
    "",
    response_model=list[UserResponse],
    operation_id="list_users",
    responses=_ADMIN_ONLY,
)
async def list_users(
    use_case: Annotated[ListUsers, Depends(get_list_users_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> list[UserResponse]:
    """List every account. Administrators only."""
    users = await use_case.handle(ListUsersQuery(), actor)
    return [UserResponse.from_domain(user) for user in users]


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
    operation_id="create_user",
    responses={
        **_ADMIN_ONLY,
        **error_response(UsernameTakenError, detail="That username is already taken."),
        **error_response(
            InvalidPasswordError, detail="A password must be 10 to 128 characters."
        ),
    },
)
async def create_user(
    payload: CreateUserRequest,
    use_case: Annotated[CreateUser, Depends(get_create_user_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> UserResponse:
    """Create an account whose initial password must be changed at first sign-in."""
    user = await use_case.handle(payload.to_command(), actor)
    return UserResponse.from_domain(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    operation_id="update_user",
    responses={
        **_ADMIN_ONLY,
        **_NOT_FOUND,
        **error_response(
            LastAdministratorError,
            detail="There must always be at least one active administrator.",
        ),
    },
)
async def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    use_case: Annotated[UpdateUser, Depends(get_update_user_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> UserResponse:
    """Rename, change the role of, disable or enable an account."""
    user = await use_case.handle(payload.to_command(user_id), actor)
    return UserResponse.from_domain(user)


@router.post(
    "/{user_id}/password",
    status_code=204,
    operation_id="reset_user_password",
    responses={
        **_ADMIN_ONLY,
        **_NOT_FOUND,
        **error_response(
            InvalidPasswordError, detail="A password must be 10 to 128 characters."
        ),
    },
)
async def reset_user_password(
    user_id: uuid.UUID,
    payload: ResetPasswordRequest,
    use_case: Annotated[ResetPassword, Depends(get_reset_password_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> None:
    """Set a new initial password, end the account's sessions and require a change."""
    await use_case.handle(payload.to_command(user_id), actor)
