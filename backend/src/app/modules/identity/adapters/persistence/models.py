import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, TimestampedMixin


class UserModel(IdentifiableMixin, TimestampedMixin, Base):
    """ORM row for a user; usernames are stored lower-cased."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str]
    password_hash: Mapped[str]
    role: Mapped[str]
    password_expired: Mapped[bool]
    disabled: Mapped[bool]
    failed_attempts: Mapped[int]
    failure_window_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionModel(IdentifiableMixin, Base):
    """ORM row for a sign-in session; only the token hash is stored."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
