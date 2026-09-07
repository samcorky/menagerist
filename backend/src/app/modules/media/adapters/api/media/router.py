import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import StreamingResponse

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.media.adapters.api.dependencies import (
    get_delete_media_use_case,
    get_get_media_use_case,
    get_media_storage,
    get_orphan_media_use_case,
    get_promote_media_use_case,
    get_stage_media_use_case,
)
from app.modules.media.adapters.api.media.schemas import MediaAssetResponse
from app.modules.media.application.delete_media import DeleteMedia, DeleteMediaCommand
from app.modules.media.application.get_media import GetMedia, GetMediaQuery
from app.modules.media.application.orphan_media import OrphanMedia, OrphanMediaCommand
from app.modules.media.application.promote_media import (
    PromoteMedia,
    PromoteMediaCommand,
)
from app.modules.media.application.stage_media import StageMedia, StageMediaCommand
from app.modules.media.domain.errors import (
    MediaAssetNotFoundError,
    MediaFileTooLargeError,
)
from app.modules.media.ports.media_storage import MediaStoragePort
from app.platform.config.media import MediaSettings, get_media_settings
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter(prefix="/media", tags=["Media"])


async def _chunks(upload: UploadFile) -> AsyncGenerator[bytes]:
    while chunk := await upload.read(64 * 1024):
        yield chunk


@router.post(
    "",
    response_model=MediaAssetResponse,
    status_code=201,
    operation_id="stage_media",
    responses=error_response(MediaFileTooLargeError, detail="upload exceeds the limit"),
)
async def stage_media(
    file: UploadFile,
    use_case: Annotated[StageMedia, Depends(get_stage_media_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    settings: Annotated[MediaSettings, Depends(get_media_settings)],
) -> MediaAssetResponse:
    """Stage an upload, streaming it to temporary storage."""
    asset = await use_case.handle(
        StageMediaCommand(
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            stream=_chunks(file),
            max_size=settings.max_upload_size,
        ),
        actor,
    )
    return MediaAssetResponse.from_domain(asset)


@router.get(
    "/{asset_id}",
    response_model=MediaAssetResponse,
    operation_id="get_media",
    responses=error_response(
        MediaAssetNotFoundError,
        detail="Media asset 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
    ),
)
async def get_media(
    asset_id: uuid.UUID,
    use_case: Annotated[GetMedia, Depends(get_get_media_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> MediaAssetResponse:
    """Fetch a media asset's metadata by id."""
    asset = await use_case.handle(GetMediaQuery(asset_id=asset_id), actor)
    return MediaAssetResponse.from_domain(asset)


@router.get(
    "/{asset_id}/content",
    operation_id="stream_media_content",
    responses={
        200: {"content": {"application/octet-stream": {}}},
        **error_response(
            MediaAssetNotFoundError,
            detail="Media asset 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
    },
)
async def stream_media_content(
    asset_id: uuid.UUID,
    get_use_case: Annotated[GetMedia, Depends(get_get_media_use_case)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> StreamingResponse:
    """Stream the binary content of a media asset."""
    asset = await get_use_case.handle(GetMediaQuery(asset_id=asset_id), actor)
    return StreamingResponse(
        storage.retrieve(asset.id, asset.status),
        media_type=asset.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{asset.filename}"',
            "Content-Length": str(asset.size),
        },
    )


@router.post(
    "/{asset_id}/promote",
    response_model=MediaAssetResponse,
    operation_id="promote_media",
    responses={
        **error_response(
            MediaAssetNotFoundError,
            detail="Media asset 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(ValidationError, detail="cannot promote a 'attached' asset"),
    },
)
async def promote_media(
    asset_id: uuid.UUID,
    use_case: Annotated[PromoteMedia, Depends(get_promote_media_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> MediaAssetResponse:
    """Promote a staged asset to attached once it has been referenced by a node."""
    asset = await use_case.handle(PromoteMediaCommand(asset_id=asset_id), actor)
    return MediaAssetResponse.from_domain(asset)


@router.post(
    "/{asset_id}/orphan",
    response_model=MediaAssetResponse,
    operation_id="orphan_media",
    responses={
        **error_response(
            MediaAssetNotFoundError,
            detail="Media asset 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(ValidationError, detail="cannot orphan a 'staged' asset"),
    },
)
async def orphan_media(
    asset_id: uuid.UUID,
    use_case: Annotated[OrphanMedia, Depends(get_orphan_media_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> MediaAssetResponse:
    """Orphan an attached asset once it has been detached from all nodes."""
    asset = await use_case.handle(OrphanMediaCommand(asset_id=asset_id), actor)
    return MediaAssetResponse.from_domain(asset)


@router.delete(
    "/{asset_id}",
    status_code=204,
    operation_id="delete_media",
    responses=error_response(
        MediaAssetNotFoundError,
        detail="Media asset 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
    ),
)
async def delete_media(
    asset_id: uuid.UUID,
    use_case: Annotated[DeleteMedia, Depends(get_delete_media_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Hard-delete a media asset and its stored file."""
    await use_case.handle(DeleteMediaCommand(asset_id=asset_id), actor)
