from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.thumbnail_eligibility import is_thumbnailable_image
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.media.ports.image_processor import ImageProcessorPort
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor

_MAX_THUMBNAILABLE_SIZE = 25 * 1024 * 1024


@dataclass(kw_only=True)
class RegenerateThumbnailsCommand:
    """Request to regenerate thumbnails for all attached, thumbnailable assets."""

    max_dimension: int = 320


class RegenerateThumbnails(
    CommandHandler[MediaUnitOfWork, RegenerateThumbnailsCommand, int]
):
    """Re-generate and re-store thumbnails for already-attached media assets.

    A backfill for assets uploaded before a thumbnailing improvement (e.g. an
    EXIF-orientation or encoder-quality fix) shipped, so their thumbnails can
    catch up without re-uploading the original file.
    """

    def __init__(
        self,
        uow: MediaUnitOfWork,
        storage: MediaStoragePort,
        image_processor: ImageProcessorPort,
    ) -> None:
        super().__init__(uow)
        self._storage = storage
        self._image_processor = image_processor

    async def handle(self, command: RegenerateThumbnailsCommand, actor: Actor) -> int:
        """Regenerate thumbnails for eligible attached assets; return the count done."""
        async with self._uow as repos:
            assets = await repos.assets.list_by_status(status=MediaStatus.ATTACHED)

        count = 0
        for asset in assets:
            if not is_thumbnailable_image(asset.content_type):
                continue
            if asset.size > _MAX_THUMBNAILABLE_SIZE:
                continue

            data = b"".join(
                [
                    chunk
                    async for chunk in self._storage.retrieve(asset.id, asset.status)
                ]
            )
            result = self._image_processor.generate_thumbnail(
                data, max_dimension=command.max_dimension
            )
            if result is None:
                continue

            await self._storage.store_thumbnail(asset.id, asset.status, result.data)
            asset.mark_thumbnail_generated()
            async with self._uow as repos:
                await repos.assets.save(asset)
                await self._uow.commit()
            count += 1
        return count
