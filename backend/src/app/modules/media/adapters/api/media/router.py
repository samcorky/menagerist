import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import StreamingResponse

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.media.adapters.api.dependencies import (
    get_attach_media_use_case,
    get_delete_media_use_case,
    get_detach_media_use_case,
    get_get_media_use_case,
    get_list_node_media_use_case,
    get_media_storage,
    get_orphan_media_use_case,
    get_promote_media_use_case,
    get_stage_media_use_case,
    get_upload_and_attach_use_case,
)
from app.modules.media.adapters.api.media.schemas import (
    MediaAssetResponse,
    MediaAttachmentResponse,
)
from app.modules.media.application.attach_media import AttachMedia, AttachMediaCommand
from app.modules.media.application.delete_media import DeleteMedia, DeleteMediaCommand
from app.modules.media.application.detach_media import DetachMedia, DetachMediaCommand
from app.modules.media.application.get_media import GetMedia, GetMediaQuery
from app.modules.media.application.list_node_media import (
    ListNodeMedia,
    ListNodeMediaQuery,
)
from app.modules.media.application.orphan_media import OrphanMedia, OrphanMediaCommand
from app.modules.media.application.promote_media import (
    PromoteMedia,
    PromoteMediaCommand,
)
from app.modules.media.application.stage_media import StageMedia, StageMediaCommand
from app.modules.media.application.upload_and_attach_media import (
    UploadAndAttachMedia,
    UploadAndAttachMediaCommand,
)
from app.modules.media.domain.errors import (
    MediaAssetNotFoundError,
    MediaAttachmentNotFoundError,
    MediaFileTooLargeError,
    UnsupportedMediaTypeError,
)
from app.modules.media.domain.media_attachment import AttachmentTarget
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


# ── Stage-only upload ──────────────────────────────────────────────────────────


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


# ── Upload + attach in one shot ────────────────────────────────────────────────


@router.post(
    "/attached",
    response_model=MediaAttachmentResponse,
    status_code=201,
    operation_id="upload_and_attach_media",
    responses={
        **error_response(MediaFileTooLargeError, detail="upload exceeds the limit"),
        **error_response(
            UnsupportedMediaTypeError, detail="content type not permitted"
        ),
    },
)
async def upload_and_attach_media(
    file: UploadFile,
    use_case: Annotated[UploadAndAttachMedia, Depends(get_upload_and_attach_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    settings: Annotated[MediaSettings, Depends(get_media_settings)],
    target_type: Annotated[AttachmentTarget, Form()],
    target_id: Annotated[uuid.UUID, Form()],
    attribute_key: Annotated[str | None, Form()] = None,
) -> MediaAttachmentResponse:
    """Stream a file to storage and attach it to a graph entity in one request."""
    attachment = await use_case.handle(
        UploadAndAttachMediaCommand(
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            stream=_chunks(file),
            target_type=target_type,
            target_id=target_id,
            attribute_key=attribute_key,
            max_size=settings.max_upload_size,
        ),
        actor,
    )
    return MediaAttachmentResponse.from_domain(attachment)


# ── Node media listing ─────────────────────────────────────────────────────────


@router.get(
    "/for-node/{node_id}",
    response_model=list[MediaAssetResponse],
    operation_id="list_node_media",
)
async def list_node_media(
    node_id: uuid.UUID,
    use_case: Annotated[ListNodeMedia, Depends(get_list_node_media_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[MediaAssetResponse]:
    """List all media assets currently attached to a node."""
    assets = await use_case.handle(ListNodeMediaQuery(node_id=node_id), actor)
    return [MediaAssetResponse.from_domain(a) for a in assets]


# ── Per-asset metadata + content ───────────────────────────────────────────────


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
    """Stream the binary content of a media asset.

    ``Content-Disposition: inline`` lets browsers render images and PDFs
    directly. For an explicit download, point an ``<a download>`` tag at this
    URL — the ``download`` attribute overrides the inline disposition
    client-side without needing a separate endpoint.
    """
    asset = await get_use_case.handle(GetMediaQuery(asset_id=asset_id), actor)
    return StreamingResponse(
        storage.retrieve(asset.id, asset.status),
        media_type=asset.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{asset.filename}"',
            "Content-Length": str(asset.size),
        },
    )


# ── Attachment management ──────────────────────────────────────────────────────


@router.post(
    "/{asset_id}/attachments",
    response_model=MediaAttachmentResponse,
    status_code=201,
    operation_id="attach_media",
    responses={
        **error_response(
            MediaAssetNotFoundError,
            detail="Media asset 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(
            UnsupportedMediaTypeError, detail="content type not permitted"
        ),
    },
)
async def attach_media(
    asset_id: uuid.UUID,
    use_case: Annotated[AttachMedia, Depends(get_attach_media_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    target_type: Annotated[AttachmentTarget, Form()],
    target_id: Annotated[uuid.UUID, Form()],
    attribute_key: Annotated[str | None, Form()] = None,
) -> MediaAttachmentResponse:
    """Attach an already-staged asset to a graph entity."""
    attachment = await use_case.handle(
        AttachMediaCommand(
            asset_id=asset_id,
            target_type=target_type,
            target_id=target_id,
            attribute_key=attribute_key,
        ),
        actor,
    )
    return MediaAttachmentResponse.from_domain(attachment)


@router.delete(
    "/{asset_id}/attachments",
    status_code=204,
    operation_id="detach_media",
    responses={
        **error_response(
            MediaAttachmentNotFoundError,
            detail="No attachment found for the given asset + target",
        ),
    },
)
async def detach_media(
    asset_id: uuid.UUID,
    use_case: Annotated[DetachMedia, Depends(get_detach_media_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    target_type: Annotated[AttachmentTarget, Form()],
    target_id: Annotated[uuid.UUID, Form()],
    attribute_key: Annotated[str | None, Form()] = None,
) -> None:
    """Remove the attachment record; orphan the asset if no other attachments remain."""
    await use_case.handle(
        DetachMediaCommand(
            asset_id=asset_id,
            target_type=target_type,
            target_id=target_id,
            attribute_key=attribute_key,
        ),
        actor,
    )


# ── Admin / repair tools (kept for operational use) ────────────────────────────


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
    """(Admin) Manually promote a staged asset without creating an attachment record."""
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
    """(Admin) Manually orphan an attached asset."""
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
