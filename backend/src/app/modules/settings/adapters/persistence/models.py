"""Saved setting values: one row per scope, owner and key."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.settings.domain.setting import SettingValue  # noqa: TC001
from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin


class SettingValueModel(IdentifiableMixin, Base):
    """A value saved by an administrator (no owner) or by a person."""

    __tablename__ = "setting_values"
    __table_args__ = (
        Index(
            "uq_setting_values_instance",
            "scope",
            "key",
            unique=True,
            postgresql_where=text("owner_id IS NULL"),
        ),
        Index(
            "uq_setting_values_owner",
            "owner_id",
            "key",
            unique=True,
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
    )

    scope: Mapped[str]
    owner_id: Mapped[UUID | None]
    key: Mapped[str]
    value: Mapped[SettingValue] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[UUID | None]
