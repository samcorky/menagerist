"""Backup operations composed once for every entrypoint.

The scheduler's worker and the CLI both run these without the API's lifespan.
"""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.platform.config.backup import get_backup_settings
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.entrypoints.api.shared.backup_media_files import BackupMediaFiles
    from app.modules.backup.domain.backup import BackupSummary
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter


@asynccontextmanager
async def media_files(
    *, scope: ContentFilter | None = None
) -> AsyncIterator[BackupMediaFiles]:
    """Keep the media repository session alive for a complete operation."""
    from app.entrypoints.api.shared.backup_media_files import BackupMediaFiles
    from app.modules.media.adapters.persistence.media_asset_repository import (
        SqlAlchemyMediaAssetRepository,
    )
    from app.modules.media.adapters.storage.local_filesystem import (
        LocalFilesystemMediaStorage,
    )
    from app.platform.config.media import get_media_settings

    async with get_session_factory()() as session:
        yield BackupMediaFiles(
            SqlAlchemyMediaAssetRepository(session),
            LocalFilesystemMediaStorage(get_media_settings().storage_path),
            scope=scope,
        )


async def create_backup(
    *,
    label: str = "manual",
    from_revision: str | None = None,
    to_revision: str | None = None,
    actor: Actor | None = None,
) -> BackupSummary:
    """Build and run a verified backup, as the system actor unless given one."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.modules.backup.adapters.persistence.database_snapshot import (
        SqlAlchemyDatabaseSnapshot,
    )
    from app.modules.backup.adapters.storage.local_backup_store import (
        LocalDirectoryBackupStore,
    )
    from app.modules.backup.application.create_backup import (
        CreateBackup,
        CreateBackupCommand,
    )
    from app.platform.app_info import load_app_info
    from app.shared_kernel.actor import SYSTEM_ACTOR

    async with media_files() as media:
        return await CreateBackup(
            LocalDirectoryBackupStore(get_backup_settings().path),
            SqlAlchemyDatabaseSnapshot(get_session_factory()),
            media,
            get_access_guard(),
            app_version=load_app_info().version,
        ).handle(
            CreateBackupCommand(
                label=label, from_revision=from_revision, to_revision=to_revision
            ),
            actor or SYSTEM_ACTOR,
        )
