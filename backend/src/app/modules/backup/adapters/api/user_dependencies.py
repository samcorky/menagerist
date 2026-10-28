from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.backup_dependencies import get_user_media_files
from app.entrypoints.api.shared.bridges.backup_user_validator import (
    BackupUserImportValidator,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.backup.adapters.api.dependencies import get_backup_workspace
from app.modules.backup.adapters.persistence.user_database_restorer import (
    SqlAlchemyUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.user_database_snapshot import (
    SqlAlchemyUserDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.application.delete_user_export import DeleteUserExport
from app.modules.backup.application.export_user_data import ExportUserData
from app.modules.backup.application.import_user_archive import ImportUserArchive
from app.modules.backup.application.import_user_data import ImportUserData
from app.modules.backup.application.list_user_exports import ListUserExports
from app.modules.backup.application.open_user_export import OpenUserExport
from app.platform.app_info import load_app_info
from app.platform.config.backup import get_backup_settings
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_workspace import BackupWorkspace
    from app.modules.backup.ports.media_files import MediaFiles
    from app.modules.backup.ports.user_database_restorer import UserDatabaseRestorer
    from app.modules.backup.ports.user_database_snapshot import UserDatabaseSnapshot
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


def get_user_backup_store(
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> BackupStore:
    """Build a private archive namespace for the signed-in account."""
    return LocalDirectoryBackupStore(
        get_backup_settings().path / "users" / str(actor.id)
    )


def get_user_database_snapshot(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> UserDatabaseSnapshot:
    """Build owner-filtered logical database snapshots."""
    return SqlAlchemyUserDatabaseSnapshot(factory)


def get_user_database_restorer(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> UserDatabaseRestorer:
    """Build transactional imports with domain validation."""
    return SqlAlchemyUserDatabaseRestorer(factory, BackupUserImportValidator())


def get_export_user_data(
    store: Annotated[BackupStore, Depends(get_user_backup_store)],
    snapshot: Annotated[UserDatabaseSnapshot, Depends(get_user_database_snapshot)],
    media: Annotated[MediaFiles, Depends(get_user_media_files)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ExportUserData:
    """Compose verified personal exports with private retention."""
    return ExportUserData(
        store,
        snapshot,
        media,
        guard,
        app_version=load_app_info().version,
        ttl_hours=get_backup_settings().user_export_ttl_hours,
    )


def get_import_user_data(
    store: Annotated[BackupStore, Depends(get_user_backup_store)],
    restorer: Annotated[UserDatabaseRestorer, Depends(get_user_database_restorer)],
    media: Annotated[MediaFiles, Depends(get_user_media_files)],
    workspace: Annotated[BackupWorkspace, Depends(get_backup_workspace)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ImportUserData:
    """Compose owner-stamped imports and reversible media writes."""
    return ImportUserData(store, restorer, media, workspace, guard)


def get_import_user_archive(
    store: Annotated[BackupStore, Depends(get_user_backup_store)],
    importer: Annotated[ImportUserData, Depends(get_import_user_data)],
    workspace: Annotated[BackupWorkspace, Depends(get_backup_workspace)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ImportUserArchive:
    """Compose bounded uploads and private import staging."""
    return ImportUserArchive(
        store,
        importer,
        workspace,
        guard,
        max_upload_size=get_backup_settings().max_upload_size,
    )


def get_open_user_export(
    store: Annotated[BackupStore, Depends(get_user_backup_store)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> OpenUserExport:
    """Compose downloads restricted to the caller's export namespace."""
    return OpenUserExport(
        store, guard, ttl_hours=get_backup_settings().user_export_ttl_hours
    )


def get_list_user_exports(
    store: Annotated[BackupStore, Depends(get_user_backup_store)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListUserExports:
    """Compose the caller's export listing with private retention."""
    return ListUserExports(
        store, guard, ttl_hours=get_backup_settings().user_export_ttl_hours
    )


def get_delete_user_export(
    store: Annotated[BackupStore, Depends(get_user_backup_store)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> DeleteUserExport:
    """Compose deletion restricted to the caller's export namespace."""
    return DeleteUserExport(
        store, guard, ttl_hours=get_backup_settings().user_export_ttl_hours
    )
