"""Durable job runs, schedule cursors and worker heartbeats.

Revision ID: x5a6b7c8d9e0
Revises: w4f5a6b7c8d9
Create Date: 2026-10-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "x5a6b7c8d9e0"
down_revision: str | None = "w4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_key", sa.String(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lane", sa.String(), nullable=False),
        sa.Column("overlap", sa.String(), nullable=False),
        sa.Column("deduplication_key", sa.Uuid(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_job_runs_deduplication_key", "job_runs", ["deduplication_key"], unique=True
    )
    op.create_index(
        "uq_job_runs_running_job",
        "job_runs",
        ["job_key"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "ix_job_runs_claim",
        "job_runs",
        ["status", "lane", "scheduled_for", "created_at", "id"],
    )
    op.create_index("ix_job_runs_history", "job_runs", ["job_key", "created_at", "id"])
    op.create_index("ix_job_runs_heartbeat", "job_runs", ["status", "heartbeat_at"])
    op.create_table(
        "schedule_cursors",
        sa.Column("job_key", sa.String(), nullable=False),
        sa.Column("expression", sa.String(), nullable=True),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("checked_until", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_key"),
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_id"),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
    op.drop_table("schedule_cursors")
    op.drop_index("ix_job_runs_heartbeat", table_name="job_runs")
    op.drop_index("ix_job_runs_history", table_name="job_runs")
    op.drop_index("ix_job_runs_claim", table_name="job_runs")
    op.drop_index("uq_job_runs_running_job", table_name="job_runs")
    op.drop_index("uq_job_runs_deduplication_key", table_name="job_runs")
    op.drop_table("job_runs")
