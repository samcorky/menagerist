"""Durable execution state, observation cursors and independent worker liveness."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin


class JobRunModel(IdentifiableMixin, Base):
    """A queued occurrence and its claimant-owned execution state."""

    __tablename__ = "job_runs"
    __table_args__ = (
        Index("uq_job_runs_deduplication_key", "deduplication_key", unique=True),
        Index(
            "uq_job_runs_running_job",
            "job_key",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        Index(
            "ix_job_runs_claim", "status", "lane", "scheduled_for", "created_at", "id"
        ),
        Index("ix_job_runs_history", "job_key", "created_at", "id"),
        Index("ix_job_runs_heartbeat", "status", "heartbeat_at"),
    )

    job_key: Mapped[str]
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lane: Mapped[str]
    overlap: Mapped[str]
    deduplication_key: Mapped[UUID | None]
    requested_by: Mapped[UUID | None]
    status: Mapped[str]
    worker_id: Mapped[str | None]
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]


class ScheduleCursorModel(Base):
    """Schedule observation state that survives run-history pruning."""

    __tablename__ = "schedule_cursors"

    job_key: Mapped[str] = mapped_column(primary_key=True)
    expression: Mapped[str | None]
    timezone: Mapped[str]
    checked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkerHeartbeatModel(Base):
    """Liveness for idle and busy workers alike."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
