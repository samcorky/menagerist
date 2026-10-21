from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.entrypoints.api.shared.authorisation import get_authorisation_port
from app.entrypoints.api.shared.backup_dependencies import (
    get_media_files,
    get_setup_gate,
)
from app.modules.backup.adapters.persistence.database_restorer import (
    SqlAlchemyDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.database_snapshot import (
    SqlAlchemyDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.adapters.storage.local_backup_workspace import (
    LocalBackupWorkspace,
)
from app.modules.backup.application.create_backup import CreateBackup
from app.modules.backup.application.delete_backup import DeleteBackup
from app.modules.backup.application.list_backups import ListBackups
from app.modules.backup.application.open_backup import OpenBackup
from app.modules.backup.application.prune_backups import PruneBackups
from app.modules.backup.application.restore_on_first_run import RestoreOnFirstRun
from app.modules.backup.application.upload_backup import UploadBackup
from app.modules.backup.application.verify_backup import VerifyBackup
from app.modules.backup.ports.backup_store import BackupStore
from app.modules.backup.ports.backup_workspace import BackupWorkspace
from app.modules.backup.ports.database_restorer import DatabaseRestorer
from app.modules.backup.ports.database_snapshot import DatabaseSnapshot
from app.modules.backup.ports.media_files import MediaFiles
from app.modules.backup.ports.setup_gate import SetupGate
from app.platform.app_info import load_app_info
from app.platform.config.backup import get_backup_settings
from app.platform.database import get_session_factory
from app.shared_kernel.authorisation import AuthorisationPort


def get_backup_store() -> BackupStore:
    """Use the configured volume for committed instance archives."""
    return LocalDirectoryBackupStore(get_backup_settings().backup_path)


def get_backup_workspace() -> BackupWorkspace:
    """Stage uploads and media rollback copies on the backup volume."""
    return LocalBackupWorkspace(get_backup_settings().backup_path)


def get_database_snapshot(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> DatabaseSnapshot:
    """Build a consistent snapshot reader over the live schema."""
    return SqlAlchemyDatabaseSnapshot(factory)


def get_database_restorer(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> DatabaseRestorer:
    """Build the transactional instance database restorer."""
    return SqlAlchemyDatabaseRestorer(factory)


def get_create_backup(
    store: Annotated[BackupStore, Depends(get_backup_store)],
    snapshot: Annotated[DatabaseSnapshot, Depends(get_database_snapshot)],
    media: Annotated[MediaFiles, Depends(get_media_files)],
    auth: Annotated[AuthorisationPort, Depends(get_authorisation_port)],
) -> CreateBackup:
    """Compose verified instance creation with original media and app metadata."""
    return CreateBackup(
        store, snapshot, media, auth, app_version=load_app_info().version
    )


def get_list_backups(
    store: Annotated[BackupStore, Depends(get_backup_store)],
    auth: Annotated[AuthorisationPort, Depends(get_authorisation_port)],
) -> ListBackups:
    """Compose the administrative committed-archive listing."""
    return ListBackups(store, auth)


def get_verify_backup(
    store: Annotated[BackupStore, Depends(get_backup_store)],
    auth: Annotated[AuthorisationPort, Depends(get_authorisation_port)],
) -> VerifyBackup:
    """Compose archive integrity verification."""
    return VerifyBackup(store, auth)


def get_open_backup(
    store: Annotated[BackupStore, Depends(get_backup_store)],
    auth: Annotated[AuthorisationPort, Depends(get_authorisation_port)],
) -> OpenBackup:
    """Compose authorised streaming downloads of instance archives."""
    return OpenBackup(store, auth)


def get_delete_backup(
    store: Annotated[BackupStore, Depends(get_backup_store)],
    auth: Annotated[AuthorisationPort, Depends(get_authorisation_port)],
) -> DeleteBackup:
    """Compose administrative archive deletion."""
    return DeleteBackup(store, auth)


def get_prune_backups(
    store: Annotated[BackupStore, Depends(get_backup_store)],
    auth: Annotated[AuthorisationPort, Depends(get_authorisation_port)],
) -> PruneBackups:
    """Apply configured instance retention and personal-export expiry."""
    settings = get_backup_settings()
    return PruneBackups(
        store,
        auth,
        keep_last=settings.keep_last,
        pre_migration_keep=settings.pre_migration_keep,
        user_export_ttl_hours=settings.user_export_ttl_hours,
    )


def get_upload_backup(
    store: Annotated[BackupStore, Depends(get_backup_store)],
    workspace: Annotated[BackupWorkspace, Depends(get_backup_workspace)],
    auth: Annotated[AuthorisationPort, Depends(get_authorisation_port)],
) -> UploadBackup:
    """Compose verified uploads with the configured archive size limit."""
    return UploadBackup(
        store, workspace, auth, max_upload_size=get_backup_settings().max_upload_size
    )


def get_restore_on_first_run(
    gate: Annotated[SetupGate, Depends(get_setup_gate)],
    store: Annotated[BackupStore, Depends(get_backup_store)],
    restorer: Annotated[DatabaseRestorer, Depends(get_database_restorer)],
    media: Annotated[MediaFiles, Depends(get_media_files)],
    workspace: Annotated[BackupWorkspace, Depends(get_backup_workspace)],
) -> RestoreOnFirstRun:
    """Compose anonymous restoration behind the existing identity setup gate."""
    return RestoreOnFirstRun(
        gate,
        store,
        restorer,
        media,
        workspace,
        max_upload_size=get_backup_settings().max_upload_size,
    )
