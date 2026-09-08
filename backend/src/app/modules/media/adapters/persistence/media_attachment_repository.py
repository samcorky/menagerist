from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from app.modules.media.adapters.persistence.models import MediaAttachmentModel
from app.modules.media.domain.media_attachment import AttachmentTarget, MediaAttachment

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


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
            attribute_key=row.attribute_key,
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

    async def add(self, attachment: MediaAttachment) -> None:
        """Persist a new attachment row."""
        self._session.add(self._to_model(attachment))
        await self._session.flush()

    async def get(self, attachment_id: uuid.UUID) -> MediaAttachment | None:
        """Return an attachment by id, or ``None``."""
        row = await self._session.get(MediaAttachmentModel, attachment_id)
        return self._to_domain(row) if row is not None else None

    async def list_for_target(
        self,
        target_type: AttachmentTarget,
        target_id: uuid.UUID,
    ) -> list[MediaAttachment]:
        """Return all attachments for the given target entity."""
        stmt = select(MediaAttachmentModel).where(
            MediaAttachmentModel.target_type == target_type.value,
            MediaAttachmentModel.target_id == target_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(r) for r in result.scalars()]

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[MediaAttachment]:
        """Return all attachments for the given asset."""
        stmt = select(MediaAttachmentModel).where(
            MediaAttachmentModel.asset_id == asset_id
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(r) for r in result.scalars()]

    async def delete(self, attachment_id: uuid.UUID) -> None:
        """Remove an attachment row by id."""
        await self._session.execute(
            delete(MediaAttachmentModel).where(MediaAttachmentModel.id == attachment_id)
        )
        await self._session.flush()
