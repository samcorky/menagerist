import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.conditional_request import ConditionalRequestDep
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http_headers import (
    conditional_get_responses,
    conditional_patch_responses,
    link_header_responses,
    link_next_header,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.presets.adapters.api.dependencies import (
    get_create_preset_use_case,
    get_delete_preset_use_case,
    get_get_preset_use_case,
    get_list_presets_use_case,
    get_update_preset_use_case,
)
from app.modules.presets.adapters.api.preset.schemas import (
    CreatePresetRequest,
    PresetResponse,
    UpdatePresetRequest,
)
from app.modules.presets.application.create_preset import CreatePreset
from app.modules.presets.application.delete_preset import (
    DeletePreset,
    DeletePresetCommand,
)
from app.modules.presets.application.get_preset import GetPreset, GetPresetQuery
from app.modules.presets.application.list_presets import ListPresets, ListPresetsQuery
from app.modules.presets.application.update_preset import UpdatePreset
from app.modules.presets.domain.errors import (
    BuiltinPresetError,
    InvalidPresetDefinitionError,
    PresetNotFoundError,
)
from app.shared_kernel.actor import Actor

router = APIRouter(prefix="/preset", tags=["Presets"], route_class=PermissionAwareRoute)

_NOT_FOUND = error_response(
    PresetNotFoundError, detail="Preset 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e30 not found"
)
_INVALID_DEFINITION = error_response(
    InvalidPresetDefinitionError, detail="a field preset needs a 'property' object"
)
_BUILTIN = error_response(
    BuiltinPresetError,
    detail="Preset 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e30 is built in and read-only",
)


@router.post(
    "",
    response_model=PresetResponse,
    status_code=201,
    operation_id="create_preset",
    responses=_INVALID_DEFINITION,
)
async def create_preset(
    payload: CreatePresetRequest,
    use_case: Annotated[CreatePreset, Depends(get_create_preset_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> PresetResponse:
    """Save a new preset (a saved field, field group or list)."""
    preset = await use_case.handle(payload.to_command(), actor)
    return PresetResponse.from_domain(preset)


@router.get(
    "/{preset_id}",
    response_model=PresetResponse,
    operation_id="get_preset",
    responses={**conditional_get_responses(), **_NOT_FOUND},
)
async def get_preset(
    preset_id: uuid.UUID,
    use_case: Annotated[GetPreset, Depends(get_get_preset_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalRequestDep,
) -> PresetResponse | Response:
    """Fetch a single preset by id."""
    preset = await use_case.handle(GetPresetQuery(preset_id=preset_id), actor)
    if earlier := cond.check_get(preset):
        return earlier
    return PresetResponse.from_domain(preset)


@router.get(
    "",
    response_model=list[PresetResponse],
    operation_id="list_presets",
    responses={**link_header_responses()},
)
async def list_presets(
    use_case: Annotated[ListPresets, Depends(get_list_presets_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    after: uuid.UUID | None = None,
    limit: int = 50,
    kind: str | None = None,
    q: str | None = None,
) -> list[PresetResponse]:
    """List presets, paginated by id, optionally filtered by kind or a label search."""
    presets = await use_case.handle(
        ListPresetsQuery(after=after, limit=limit + 1, kind=kind, q=q), actor
    )
    if len(presets) > limit:
        response.headers["Link"] = link_next_header(request, str(presets[limit - 1].id))

    return [PresetResponse.from_domain(p) for p in presets[:limit]]


@router.patch(
    "/{preset_id}",
    response_model=PresetResponse,
    operation_id="update_preset",
    responses={
        **conditional_patch_responses(),
        **_NOT_FOUND,
        **_INVALID_DEFINITION,
        **_BUILTIN,
    },
)
async def update_preset(
    preset_id: uuid.UUID,
    payload: UpdatePresetRequest,
    get_usecase: Annotated[GetPreset, Depends(get_get_preset_use_case)],
    update_usecase: Annotated[UpdatePreset, Depends(get_update_preset_use_case)],
    cond: ConditionalRequestDep,
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> PresetResponse | Response:
    """Update a preset's editable fields. Setting `definition` bumps `version`."""
    current = await get_usecase.handle(GetPresetQuery(preset_id=preset_id), actor)
    if earlier := cond.check_patch(current):
        return earlier
    preset = await update_usecase.handle(payload.to_command(preset_id), actor)
    cond.set_response_etag(preset)
    return PresetResponse.from_domain(preset)


@router.delete(
    "/{preset_id}",
    status_code=204,
    operation_id="delete_preset",
    responses={**_NOT_FOUND, **_BUILTIN},
)
async def delete_preset(
    preset_id: uuid.UUID,
    use_case: Annotated[DeletePreset, Depends(get_delete_preset_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete a preset."""
    await use_case.handle(DeletePresetCommand(preset_id=preset_id), actor)
