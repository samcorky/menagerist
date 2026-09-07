from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.media.adapters.persistence.unit_of_work import create_media_uow
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.application.cleanup_expired_media import CleanupExpiredMedia
from app.modules.media.application.delete_media import DeleteMedia
from app.modules.media.application.get_media import GetMedia
from app.modules.media.application.orphan_media import OrphanMedia
from app.modules.media.application.promote_media import PromoteMedia
from app.modules.media.application.stage_media import StageMedia
from app.modules.media.ports.media_storage import MediaStoragePort
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.platform.config.media import MediaSettings, get_media_settings
from app.platform.database import get_session_factory


def get_media_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> MediaUnitOfWork:
    return create_media_uow(session_factory)


def get_media_storage(
    settings: Annotated[MediaSettings, Depends(get_media_settings)],
) -> MediaStoragePort:
    return LocalFilesystemMediaStorage(settings.media_storage_path)


def get_stage_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
) -> StageMedia:
    return StageMedia(uow, storage)


def get_get_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
) -> GetMedia:
    return GetMedia(uow)


def get_promote_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
) -> PromoteMedia:
    return PromoteMedia(uow, storage)


def get_orphan_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
) -> OrphanMedia:
    return OrphanMedia(uow, storage)


def get_delete_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
) -> DeleteMedia:
    return DeleteMedia(uow, storage)


def get_cleanup_expired_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
) -> CleanupExpiredMedia:
    return CleanupExpiredMedia(uow, storage)
