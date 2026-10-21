from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.modules.media.adapters.persistence.models import (
    MediaAssetModel,
    MediaAttachmentModel,
)
from app.modules.media.domain.errors import CoverAlreadySetError
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.platform.orm_mixins import owned_by

if TYPE_CHECKING:
    import uuid

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()

_COVER_INDEX = "uq_media_attachment_cover"


def _visible(scope: ContentFilter) -> Select[tuple[MediaAttachmentModel]]:
    """Select attachments whose asset is inside `scope`."""
    return (
        select(MediaAttachmentModel)
        .join(MediaAssetModel, MediaAssetModel.id == MediaAttachmentModel.asset_id)
        .where(owned_by(MediaAssetModel, scope.user_id))
    )


class SqlAlchemyMediaAttachmentRepository:
    """SQLAlchemy-backed `MediaAttachmentRepository` using the polymorphic table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: MediaAttachmentModel) -> MediaAttachment:
        return MediaAttachment(
            id=row.id,
            asset_id=row.asset_id,
            target_type=AttachmentTarget(row.target_type),
            target_id=row.target_id,
            attribute_key=AttachmentKey(row.attribute_key)
            if row.attribute_key
            else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_model(self, attachment: MediaAttachment) -> MediaAttachmentModel:
        return MediaAttachmentModel(
            id=attachment.id,
            asset_id=attachment.asset_id,
            target_type=attachment.target_type.value,
            target_id=attachment.target_id,
            attribute_key=attachment.attribute_key,
            created_at=attachment.created_at,
            updated_at=attachment.updated_at,
        )

    async def lock_target(
        self, target_type: AttachmentTarget, target_id: uuid.UUID
    ) -> None:
        """Take a transaction-scoped advisory lock on the target's cover."""
        key = f"media-cover:{target_type.value}:{target_id}"
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0)))
        )

    async def add(self, attachment: MediaAttachment) -> None:
        """Persist a new attachment row.

        Raises:
            CoverAlreadySetError: If it is a second cover for its target.
        """
        logger.debug(
            "adding media attachment",
            attachment_id=attachment.id,
            asset_id=attachment.asset_id,
        )
        try:
            # A savepoint keeps the session usable after a rejected insert.
            async with self._session.begin_nested():
                self._session.add(self._to_model(attachment))
        except IntegrityError as exc:
            if _COVER_INDEX not in str(exc.orig):
                raise
            raise CoverAlreadySetError from exc

    async def get(
        self, attachment_id: uuid.UUID, *, scope: ContentFilter
    ) -> MediaAttachment | None:
        """Return an attachment by id, or ``None`` if missing or unseen."""
        logger.debug("fetching media attachment", attachment_id=attachment_id)
        stmt = _visible(scope).where(MediaAttachmentModel.id == attachment_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def list_for_target(
        self,
        target_type: AttachmentTarget,
        target_id: uuid.UUID,
        *,
        scope: ContentFilter,
    ) -> list[MediaAttachment]:
        """Return the attachments on the target whose asset is inside `scope`."""
        logger.debug(
            "listing attachments for target",
            target_type=target_type.value,
            target_id=target_id,
        )
        stmt = _visible(scope).where(
            MediaAttachmentModel.target_type == target_type.value,
            MediaAttachmentModel.target_id == target_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(r) for r in result.scalars()]

    async def list_for_asset(
        self, asset_id: uuid.UUID, *, scope: ContentFilter
    ) -> list[MediaAttachment]:
        """Return the attachments of the asset, if the asset is inside `scope`."""
        logger.debug("listing attachments for asset", asset_id=asset_id)
        stmt = _visible(scope).where(MediaAttachmentModel.asset_id == asset_id)
        result = await self._session.execute(stmt)
        return [self._to_domain(r) for r in result.scalars()]

    async def update(self, attachment: MediaAttachment) -> None:
        """Persist changes to an existing attachment row."""
        logger.debug("updating media attachment", attachment_id=attachment.id)
        row = await self._session.get(MediaAttachmentModel, attachment.id)
        if row is None:
            return
        row.attribute_key = attachment.attribute_key
        row.updated_at = attachment.updated_at
        await self._session.flush()

    async def delete(self, attachment_id: uuid.UUID) -> None:
        """Remove an attachment row by id."""
        logger.debug("deleting media attachment", attachment_id=attachment_id)
        await self._session.execute(
            delete(MediaAttachmentModel).where(MediaAttachmentModel.id == attachment_id)
        )
        await self._session.flush()
