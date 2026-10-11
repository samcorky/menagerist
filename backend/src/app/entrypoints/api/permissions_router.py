from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from app.entrypoints.api.shared.authorization import RoleAuthorizationAdapter
from app.entrypoints.api.shared.dependencies import (
    get_current_actor,
    get_role_authorization,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.entrypoints.api.shared.permissions import Permission
from app.shared_kernel.actor import Actor

router = APIRouter(
    prefix="/auth", tags=["Authentication"], route_class=PermissionAwareRoute
)


class PermissionsResponse(BaseModel):
    """The permissions the signed-in account holds."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"permissions": ["graph:node_type:delete"]}]}
    )

    permissions: list[Permission]


@router.get(
    "/me/permissions",
    response_model=PermissionsResponse,
    operation_id="get_my_permissions",
)
async def get_my_permissions(
    response: Response,
    actor: Annotated[Actor, Depends(get_current_actor)],
    authorization: Annotated[RoleAuthorizationAdapter, Depends(get_role_authorization)],
) -> PermissionsResponse:
    """List the permissions the signed-in account holds, implications included."""
    response.headers["Cache-Control"] = "private, no-store"
    return PermissionsResponse(
        permissions=sorted(authorization.effective_permissions(actor))
    )
