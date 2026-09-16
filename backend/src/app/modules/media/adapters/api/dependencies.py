from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.media.adapters.imaging.pillow_processor import PillowImageProcessor
from app.modules.media.adapters.persistence.unit_of_work import (
    build_media_repos,
    create_media_uow,
)
from app.modules.media.adapters.policy.content_type_attachment_policy import (
    ContentTypeAttachmentPolicy,
)
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.application.attach_media import AttachMedia
from app.modules.media.application.cleanup_expired_media import CleanupExpiredMedia
from app.modules.media.application.clear_media_cover import ClearMediaCover
from app.modules.media.application.delete_media import DeleteMedia
from app.modules.media.application.detach_media import DetachMedia
from app.modules.media.application.get_media import GetMedia
from app.modules.media.application.list_node_media import ListNodeMedia
from app.modules.media.application.orphan_media import OrphanMedia
from app.modules.media.application.promote_media import PromoteMedia
from app.modules.media.application.set_media_cover import SetMediaCover
from app.modules.media.application.stage_media import StageMedia
from app.modules.media.application.update_media import UpdateMedia
from app.modules.media.application.upload_and_attach_media import UploadAndAttachMedia
from app.modules.media.ports.attachment_policy import AttachmentPolicyPort
from app.modules.media.ports.image_processor import ImageProcessorPort
from app.modules.media.ports.media_storage import MediaStoragePort
from app.modules.media.ports.unit_of_work import MediaRepos, MediaUnitOfWork
from app.platform.config.media import MediaSettings, get_media_settings
from app.platform.database import get_session_factory


def get_media_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> MediaUnitOfWork:
    return create_media_uow(session_factory)


async def get_media_repos(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[MediaRepos]:
    """Return a read-only repository bundle over the media tables, for queries."""
    async with session_factory() as session:
        yield build_media_repos(session)


def get_media_storage(
    settings: Annotated[MediaSettings, Depends(get_media_settings)],
) -> MediaStoragePort:
    return LocalFilesystemMediaStorage(settings.media_storage_path)


def get_attachment_policy() -> AttachmentPolicyPort:
    return ContentTypeAttachmentPolicy()


def get_image_processor() -> ImageProcessorPort:
    return PillowImageProcessor()


def get_stage_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    image_processor: Annotated[ImageProcessorPort, Depends(get_image_processor)],
) -> StageMedia:
    return StageMedia(uow, storage, image_processor)


def get_get_media_use_case(
    repos: Annotated[MediaRepos, Depends(get_media_repos)],
) -> GetMedia:
    return GetMedia(repos)


def get_promote_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
) -> PromoteMedia:
    return PromoteMedia(uow, storage)


def get_update_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
) -> UpdateMedia:
    return UpdateMedia(uow)


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


def get_attach_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    policy: Annotated[AttachmentPolicyPort, Depends(get_attachment_policy)],
) -> AttachMedia:
    return AttachMedia(uow, storage, policy)


def get_detach_media_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
) -> DetachMedia:
    return DetachMedia(uow, storage)


def get_set_media_cover_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
) -> SetMediaCover:
    return SetMediaCover(uow)


def get_clear_media_cover_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
) -> ClearMediaCover:
    return ClearMediaCover(uow)


def get_upload_and_attach_use_case(
    uow: Annotated[MediaUnitOfWork, Depends(get_media_uow)],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    policy: Annotated[AttachmentPolicyPort, Depends(get_attachment_policy)],
    image_processor: Annotated[ImageProcessorPort, Depends(get_image_processor)],
) -> UploadAndAttachMedia:
    return UploadAndAttachMedia(uow, storage, policy, image_processor)


def get_list_node_media_use_case(
    repos: Annotated[MediaRepos, Depends(get_media_repos)],
) -> ListNodeMedia:
    return ListNodeMedia(repos)
