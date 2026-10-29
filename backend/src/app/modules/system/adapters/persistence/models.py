"""The stored result of the latest release check for each source and channel."""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base


class UpdateCheckModel(Base):
    """One row per repository and channel, so a result is never reused across them."""

    __tablename__ = "update_checks"

    key: Mapped[str] = mapped_column(primary_key=True)
    source: Mapped[str]
    channel: Mapped[str]
    latest_version: Mapped[str | None]
    latest_url: Mapped[str | None]
    latest_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    latest_prerelease: Mapped[bool] = mapped_column(default=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failure: Mapped[str | None]
