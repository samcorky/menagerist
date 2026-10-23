from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.upload_limit_middleware import (
    PAYLOAD_TOO_LARGE_RESPONSE,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.backup.adapters.api.router import ARCHIVE_BODY
from app.modules.backup.adapters.api.schemas import BackupResponse
from app.modules.backup.adapters.api.user_dependencies import (
    get_export_user_data,
    get_import_user_archive,
    get_open_user_export,
)
from app.modules.backup.application.export_user_data import (
    ExportUserData,
    ExportUserDataCommand,
)
from app.modules.backup.application.import_user_archive import (
    ImportUserArchive,
    ImportUserArchiveCommand,
)
from app.modules.backup.application.open_user_export import (
    OpenUserExport,
    OpenUserExportQuery,
)
from app.shared_kernel.actor import Actor

router = APIRouter(
    prefix="/me", tags=["Personal backups"], route_class=PermissionAwareRoute
)


@router.post(
    "/export",
    status_code=201,
    response_model=BackupResponse,
    operation_id="export_user_data",
    responses={
        201: {
            "links": {
                "DownloadExport": {
                    "operationId": "download_user_export",
                    "parameters": {"backup_id": "$response.body#/id"},
                    "description": "Download the archive that was just created.",
                }
            }
        }
    },
)
async def export_user_data(
    use_case: Annotated[ExportUserData, Depends(get_export_user_data)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> BackupResponse:
    """Create a verified archive of the caller's content."""
    return BackupResponse.model_validate(
        await use_case.handle(ExportUserDataCommand(), actor)
    )


@router.get(
    "/export/{backup_id}/download",
    operation_id="download_user_export",
    responses={
        200: {
            "description": "The caller's personal archive.",
            "content": {
                "application/gzip": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def download_user_export(
    backup_id: UUID,
    use_case: Annotated[OpenUserExport, Depends(get_open_user_export)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> StreamingResponse:
    """Stream an archive from the caller's private namespace."""
    opened = await use_case.handle(OpenUserExportQuery(backup_id=backup_id), actor)
    return StreamingResponse(
        opened.chunks,
        media_type="application/gzip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="menagerist-personal-{backup_id}.tar.gz"'
            ),
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/import",
    status_code=204,
    operation_id="import_user_data",
    openapi_extra=ARCHIVE_BODY,
    responses={
        **PAYLOAD_TOO_LARGE_RESPONSE,
        409: {
            "description": (
                "The account contains content or the archive is incompatible."
            )
        },
    },
)
async def import_user_data(
    request: Request,
    use_case: Annotated[ImportUserArchive, Depends(get_import_user_archive)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> Response:
    """Import a verified personal archive into the caller's account."""
    await use_case.handle(ImportUserArchiveCommand(stream=request.stream()), actor)
    return Response(status_code=204)
