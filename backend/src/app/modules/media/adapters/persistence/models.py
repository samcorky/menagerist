import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, TimestampedMixin


class MediaAssetModel(IdentifiableMixin, TimestampedMixin, Base):
    """ORM row for a media asset - the storage shape, kept separate from the domain."""

    __tablename__ = "media_assets"

    filename: Mapped[str]
    content_type: Mapped[str]
    size: Mapped[int]
    sha256: Mapped[str]
    status: Mapped[str] = mapped_column(index=True)


class MediaAttachmentModel(IdentifiableMixin, TimestampedMixin, Base):
    """Polymorphic junction table linking a media asset to any graph entity.

    ``target_type`` is the ``AttachmentTarget`` string value (``"node"``,
    ``"edge"``, …); ``target_id`` is the PK of the referenced row.  No FK
    constraint on ``target_id`` — referential integrity is enforced by the
    application layer, which also handles cascade deletion.
    """

    __tablename__ = "media_attachments"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "target_type",
            "target_id",
            "attribute_key",
            name="uq_media_attachment",
        ),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(index=True)
    attribute_key: Mapped[str | None]
