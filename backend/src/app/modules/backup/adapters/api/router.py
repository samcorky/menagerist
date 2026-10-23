from datetime import UTC
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from app.entrypoints.api.shared.bridges.backup_setup_gate import first_run_restore_slot
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.cross_site import refuse_cross_site
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.http.upload_limit_middleware import (
    PAYLOAD_TOO_LARGE_RESPONSE,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.backup.adapters.api.dependencies import (
    get_create_backup,
    get_delete_backup,
    get_list_backups,
    get_open_backup,
    get_prune_backups,
    get_restore_on_first_run,
    get_upload_backup,
    get_verify_backup,
)
from app.modules.backup.adapters.api.schemas import (
    BackupResponse,
    CreateBackupRequest,
    PruneBackupsRequest,
    PruneResponse,
    VerificationResponse,
)
from app.modules.backup.application.create_backup import CreateBackup
from app.modules.backup.application.delete_backup import (
    DeleteBackup,
    DeleteBackupCommand,
)
from app.modules.backup.application.list_backups import ListBackups, ListBackupsQuery
from app.modules.backup.application.open_backup import OpenBackup, OpenBackupQuery
from app.modules.backup.application.prune_backups import PruneBackups
from app.modules.backup.application.restore_on_first_run import (
    RestoreOnFirstRun,
    RestoreOnFirstRunCommand,
)
from app.modules.backup.application.upload_backup import (
    UploadBackup,
    UploadBackupCommand,
)
from app.modules.backup.application.verify_backup import VerifyBackup, VerifyBackupQuery
from app.modules.backup.domain.errors import (
    BackupNotFoundError,
    CorruptBackupError,
    RestoreTargetNotEmptyError,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.slug import slugify

router = APIRouter(prefix="/backup", tags=["Backups"], route_class=PermissionAwareRoute)
public_router = APIRouter(
    prefix="/backup", tags=["Backups"], route_class=PermissionAwareRoute
)

ARCHIVE_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/gzip": {"schema": {"type": "string", "format": "binary"}}
        },
    }
}
ADMIN_RESPONSES: dict[int | str, dict[str, Any]] = error_response(
    ForbiddenError,
    detail="You do not have permission to do that.",
    description="Administrator permission required.",
)
_BACKUP_NOT_FOUND = error_response(
    BackupNotFoundError,
    detail="Backup 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e40 was not found.",
)


@router.post(
    "",
    status_code=201,
    response_model=BackupResponse,
    operation_id="create_backup",
    responses=ADMIN_RESPONSES,
)
async def create_backup(
    payload: CreateBackupRequest,
    use_case: Annotated[CreateBackup, Depends(get_create_backup)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> BackupResponse:
    """Create and verify an instance archive."""
    return BackupResponse.model_validate(
        await use_case.handle(payload.to_command(), actor)
    )


@router.get(
    "",
    response_model=list[BackupResponse],
    operation_id="list_backups",
    responses=ADMIN_RESPONSES,
)
async def list_backups(
    use_case: Annotated[ListBackups, Depends(get_list_backups)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[BackupResponse]:
    """List committed instance archive summaries."""
    return [
        BackupResponse.model_validate(row)
        for row in await use_case.handle(ListBackupsQuery(), actor)
    ]


@router.post(
    "/prune",
    response_model=PruneResponse,
    operation_id="prune_backups",
    responses=ADMIN_RESPONSES,
)
async def prune_backups(
    payload: PruneBackupsRequest,
    use_case: Annotated[PruneBackups, Depends(get_prune_backups)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> PruneResponse:
    """Preview or apply separate ordinary and migration retention."""
    return PruneResponse.model_validate(
        await use_case.handle(payload.to_command(), actor)
    )


@router.post(
    "/upload",
    status_code=201,
    response_model=BackupResponse,
    operation_id="upload_backup",
    openapi_extra=ARCHIVE_BODY,
    responses={**ADMIN_RESPONSES, **PAYLOAD_TOO_LARGE_RESPONSE},
)
async def upload_backup(
    request: Request,
    use_case: Annotated[UploadBackup, Depends(get_upload_backup)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> BackupResponse:
    """Upload a gzip archive as a streamed request body."""
    return BackupResponse.model_validate(
        await use_case.handle(UploadBackupCommand(stream=request.stream()), actor)
    )


@public_router.post(
    "/first-run-restore",
    status_code=204,
    operation_id="restore_on_first_run",
    openapi_extra=ARCHIVE_BODY,
    dependencies=[Depends(refuse_cross_site), Depends(first_run_restore_slot)],
    responses={
        **error_response(
            RestoreTargetNotEmptyError,
            detail="Restore would overwrite existing instance content.",
            description="Setup has already been completed or the target is not empty.",
        ),
        **error_response(
            CorruptBackupError,
            detail="The archive failed integrity or structural validation.",
            description="The archive failed verification.",
        ),
        **PAYLOAD_TOO_LARGE_RESPONSE,
    },
)
async def restore_on_first_run(
    request: Request,
    use_case: Annotated[RestoreOnFirstRun, Depends(get_restore_on_first_run)],
) -> Response:
    """Restore an empty instance using the archived accounts and credentials."""
    await use_case.handle(
        RestoreOnFirstRunCommand(stream=request.stream()), ANONYMOUS_ACTOR
    )
    return Response(status_code=204)


@router.post(
    "/{backup_id}/verify",
    response_model=VerificationResponse,
    operation_id="verify_backup",
    responses={**ADMIN_RESPONSES, **_BACKUP_NOT_FOUND},
)
async def verify_backup(
    backup_id: UUID,
    use_case: Annotated[VerifyBackup, Depends(get_verify_backup)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> VerificationResponse:
    """Check every archive member and its compressed digest."""
    return VerificationResponse.model_validate(
        await use_case.handle(VerifyBackupQuery(backup_id=backup_id), actor)
    )


@router.get(
    "/{backup_id}/download",
    operation_id="download_backup",
    responses={
        **ADMIN_RESPONSES,
        **_BACKUP_NOT_FOUND,
        200: {
            "description": "The compressed backup archive.",
            "content": {
                "application/gzip": {"schema": {"type": "string", "format": "binary"}}
            },
        },
    },
)
async def download_backup(
    backup_id: UUID,
    use_case: Annotated[OpenBackup, Depends(get_open_backup)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> StreamingResponse:
    """Stream the committed compressed archive."""
    opened = await use_case.handle(OpenBackupQuery(backup_id=backup_id), actor)
    label = slugify(opened.summary.label)[:120].rstrip("-") or "backup"
    date = opened.summary.created_at.astimezone(UTC).date().isoformat()
    filename = f"menagerist-{label}-{date}-{backup_id}.tar.gz"
    return StreamingResponse(
        opened.chunks,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "/{backup_id}",
    status_code=204,
    operation_id="delete_backup",
    responses={**ADMIN_RESPONSES, **_BACKUP_NOT_FOUND},
)
async def delete_backup(
    backup_id: UUID,
    use_case: Annotated[DeleteBackup, Depends(get_delete_backup)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> Response:
    """Delete a committed instance archive."""
    await use_case.handle(DeleteBackupCommand(backup_id=backup_id), actor)
    return Response(status_code=204)
