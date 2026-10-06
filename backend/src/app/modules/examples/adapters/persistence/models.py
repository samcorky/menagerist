from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, TimestampedMixin


class ExampleInstallationModel(IdentifiableMixin, TimestampedMixin, Base):
    """ORM row for an example pack installation."""

    __tablename__ = "example_installations"
    # A backstop only: `InstallExamplePack` already refuses a second active install.
    __table_args__ = (
        Index(
            "uq_example_installations_active_pack",
            "pack_id",
            unique=True,
            postgresql_where=text("status IN ('installing', 'installed')"),
        ),
    )

    pack_id: Mapped[str] = mapped_column(index=True)
    status: Mapped[str]
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
