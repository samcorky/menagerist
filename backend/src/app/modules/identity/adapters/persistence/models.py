import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, PrimaryKeyConstraint
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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionModel(IdentifiableMixin, Base):
    """ORM row for a sign-in session; only the token hash is stored."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SignInAttemptModel(Base):
    """ORM row for a failure counter; the key is a hash, never the raw value."""

    __tablename__ = "sign_in_attempts"
    __table_args__ = (
        PrimaryKeyConstraint("key_type", "key_hash"),
        Index("ix_sign_in_attempts_window_start", "window_start"),
    )

    key_type: Mapped[str]
    key_hash: Mapped[str]
    failure_count: Mapped[int]
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
