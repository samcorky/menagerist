import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.content_type_safety import (
    guessed_type_matches,
    resolve_trusted_content_type,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.thumbnail_eligibility import is_thumbnailable_image
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.media.ports.image_processor import ImageProcessorPort
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger(__name__)

_MAX_THUMBNAILABLE_SIZE = 25 * 1024 * 1024  # skip thumbnailing above this, not an error


@dataclass(kw_only=True)
class StageMediaCommand:
    """Request to stage a new media upload."""

    filename: str
    content_type: str
    stream: "AsyncIterator[bytes]"
    sniffed_content_type: str | None = field(default=None)
    max_size: int | None = field(default=None)


class StageMedia(CommandHandler[MediaUnitOfWork, StageMediaCommand, MediaAsset]):
    """Stream an upload to staging storage and record it in the database."""

    def __init__(
        self,
        uow: MediaUnitOfWork,
        storage: MediaStoragePort,
        image_processor: ImageProcessorPort,
    ) -> None:
        super().__init__(uow)
        self._storage = storage
        self._image_processor = image_processor

    async def handle(self, command: StageMediaCommand, actor: Actor) -> MediaAsset:
        """Write the stream to staged storage, then persist the asset record.

        The id is pre-generated so the storage adapter knows the destination path
        before the DB row is written.
        """
        asset_id = uuid.uuid7()

        if not guessed_type_matches(command.filename, command.content_type):
            logger.warning(
                "media content-type does not match filename extension",
                asset_id=str(asset_id),
                filename=command.filename,
                declared_content_type=command.content_type,
            )

        trusted_content_type = resolve_trusted_content_type(
            command.content_type, command.sniffed_content_type
        )
        if trusted_content_type != command.content_type:
            logger.warning(
                "media content-type downgraded: unconfirmed by signature",
                asset_id=str(asset_id),
                filename=command.filename,
                declared_content_type=command.content_type,
                sniffed_content_type=command.sniffed_content_type,
            )

        size, sha256 = await self._storage.store(
            asset_id,
            MediaStatus.STAGED,
            command.stream,
            max_size=command.max_size,
        )

        asset = MediaAsset.create(
            asset_id=asset_id,
            filename=command.filename,
            content_type=trusted_content_type,
            size=size,
            sha256=sha256,
        )

        if (
            is_thumbnailable_image(trusted_content_type)
            and size <= _MAX_THUMBNAILABLE_SIZE
        ):
            thumbnail_data = b"".join(
                [
                    chunk
                    async for chunk in self._storage.retrieve(
                        asset_id, MediaStatus.STAGED
                    )
                ]
            )
            if result := self._image_processor.generate_thumbnail(thumbnail_data):
                await self._storage.store_thumbnail(
                    asset_id, MediaStatus.STAGED, result.data
                )
                asset.mark_thumbnail_generated()

        async with self._uow as repos:
            await repos.assets.add(asset)
            await self._uow.commit()
        logger.info("media staged", asset_id=asset.id, filename=command.filename)
        return asset
