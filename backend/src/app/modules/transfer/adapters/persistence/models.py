import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, OwnedMixin, TimestampedMixin


class RunModel(IdentifiableMixin, OwnedMixin, TimestampedMixin, Base):
    """ORM row for a bundle run.

    The table and `pack_id` keep the names they had when only example packs were
    installed, so moving the ledger into `transfer` needed no migration.
    """

    __tablename__ = "example_installations"
    # The unique index is a backstop only: the installer already refuses a second
    # active run of a bundle by the same person.
    __table_args__ = (
        Index(
            "uq_example_installations_active_pack",
            "pack_id",
            "owner_id",
            unique=True,
            postgresql_where=text("status IN ('installing', 'installed')"),
        ),
        Index("ix_example_installations_owner_id_id", "owner_id", "id"),
    )

    pack_id: Mapped[str] = mapped_column(index=True)
    status: Mapped[str]
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceLinkModel(IdentifiableMixin, OwnedMixin, TimestampedMixin, Base):
    """ORM row for a source link: a source's key for an entity and what was imported."""

    __tablename__ = "source_links"
    __table_args__ = (
        Index(
            "uq_source_links_owner_source_kind_key",
            "owner_id",
            "source",
            "kind",
            "key",
            unique=True,
        ),
        Index("ix_source_links_owner_id_source", "owner_id", "source"),
    )

    source: Mapped[str]
    kind: Mapped[str]
    key: Mapped[str]
    entity_id: Mapped[uuid.UUID]
    fields: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ItemImportModel(IdentifiableMixin, OwnedMixin, TimestampedMixin, Base):
    """ORM row for an uploaded import file and what became of it."""

    __tablename__ = "item_imports"
    __table_args__ = (
        Index("ix_item_imports_owner_id_id", "owner_id", "id"),
        Index("ix_item_imports_status_queued_at", "status", "queued_at"),
        Index("ix_item_imports_expires_at", "expires_at"),
    )

    filename: Mapped[str]
    size: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str]
    options: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    grants: Mapped[list[str] | None] = mapped_column(JSONB)
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    outcome: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    failure: Mapped[str | None]
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
