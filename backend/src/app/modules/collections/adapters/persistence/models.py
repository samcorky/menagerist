import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, SoftDeletableMixin


class CollectionModel(IdentifiableMixin, SoftDeletableMixin, Base):
    """ORM row for a collection."""

    __tablename__ = "collections"
    # Only live rows reserve a slug; the use cases check this too, the index backs them.
    __table_args__ = (
        Index(
            "uq_collections_slug_live",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str]
    slug: Mapped[str]
    description: Mapped[str | None]
    kind: Mapped[str]
    owner_id: Mapped[uuid.UUID]
    visibility: Mapped[str]


class CollectionMemberModel(Base):
    """ORM row placing an item on a collection.

    `item_id` has no foreign key: items belong to another module.
    """

    __tablename__ = "collection_members"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
