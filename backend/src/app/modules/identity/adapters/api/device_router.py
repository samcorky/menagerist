import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_rename_device_use_case,
)
from app.modules.identity.adapters.api.schemas import (
    DEVICE_NAME_EXAMPLE,
    DeviceNameResponse,
    RenameDeviceRequest,
)
from app.modules.identity.application.rename_device import (
    RenameDevice,
    RenameDeviceCommand,
)
from app.modules.identity.domain.errors import (
    DeviceNotFoundError,
    InvalidDeviceNameError,
    SessionRequiredError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

router = APIRouter(
    prefix="/devices", tags=["Sessions"], route_class=PermissionAwareRoute
)


@router.patch(
    "/{device_id}",
    response_model=DeviceNameResponse,
    operation_id="rename_device",
    responses={
        200: {"content": {"application/json": {"example": DEVICE_NAME_EXAMPLE}}},
        **error_response(SessionRequiredError, detail="Sign in to continue."),
        **error_response(
            ForbiddenError, detail="You do not have permission to do that."
        ),
        **error_response(DeviceNotFoundError, detail="That device was not found."),
        **error_response(
            InvalidDeviceNameError, detail="A device name can be at most 60 characters."
        ),
    },
)
async def rename_device(
    device_id: Annotated[uuid.UUID, Path(description="The device to rename.")],
    payload: RenameDeviceRequest,
    use_case: Annotated[RenameDevice, Depends(get_rename_device_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> DeviceNameResponse:
    """Rename any user's device, or clear its name. Administrators only."""
    device = await use_case.handle(
        RenameDeviceCommand(device_id=device_id, name=payload.name), actor
    )
    return DeviceNameResponse.from_domain(device)
