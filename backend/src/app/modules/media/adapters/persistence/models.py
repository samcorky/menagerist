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
