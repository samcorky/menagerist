from typing import Any

from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, OwnedMixin, SoftDeletableMixin


class PresetModel(IdentifiableMixin, OwnedMixin, SoftDeletableMixin, Base):
    """ORM row for a preset - the storage shape, kept separate from `domain.Preset`."""

    __tablename__ = "presets"
    __table_args__ = (Index("ix_presets_owner_id_id", "owner_id", "id"),)

    kind: Mapped[str] = mapped_column(index=True)
    label: Mapped[str]
    description: Mapped[str | None]
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(default=1)
