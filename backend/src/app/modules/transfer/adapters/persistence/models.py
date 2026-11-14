from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, text
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
