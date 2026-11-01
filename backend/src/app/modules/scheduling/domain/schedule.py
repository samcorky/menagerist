"""Pure missed-run policy, independent of the cron parser and clock."""

from datetime import UTC, datetime, timedelta

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.jobs import MissedRun


def due_fire(
    latest: datetime | None,
    *,
    watermark: datetime | None,
    now: datetime,
    missed: MissedRun,
    max_lateness: timedelta,
) -> datetime | None:
    """Select an eligible occurrence; a new job never backfills history."""
    for moment in (latest, watermark, now):
        if moment is not None and moment.utcoffset() is None:
            raise ValidationError("Timezone-aware datetimes are required")
    if watermark is None or latest is None:
        return None
    latest = latest.astimezone(UTC)
    watermark = watermark.astimezone(UTC)
    now = now.astimezone(UTC)
    if not watermark < latest <= now:
        return None
    grace = max_lateness if missed is MissedRun.RUN_ONCE else timedelta(minutes=1)
    return latest if now - latest <= grace else None
