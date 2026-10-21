from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.backup_media_files import BackupMediaFiles
from app.entrypoints.api.shared.bridges.backup_setup_gate import (
    get_setup_gate as get_setup_gate,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.platform.config.media import get_media_settings
from app.platform.database import get_session_factory
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.backup.ports.media_files import MediaFiles
    from app.shared_kernel.actor import Actor


async def get_media_files(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[MediaFiles]:
    """Yield original media access for the whole instance."""
    async with factory() as session:
        yield BackupMediaFiles(
            SqlAlchemyMediaAssetRepository(session),
            LocalFilesystemMediaStorage(get_media_settings().media_storage_path),
        )


async def get_user_media_files(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> AsyncIterator[MediaFiles]:
    """Yield original media access scoped to the signed-in account."""
    async with factory() as session:
        yield BackupMediaFiles(
            SqlAlchemyMediaAssetRepository(session),
            LocalFilesystemMediaStorage(get_media_settings().media_storage_path),
            scope=ContentFilter.of(actor.id),
        )
