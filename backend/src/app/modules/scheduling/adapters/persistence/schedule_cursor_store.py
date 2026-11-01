"""Durable observation windows coordinated with each job's queue."""

from typing import TYPE_CHECKING

from app.modules.scheduling.adapters.persistence.job_lock import lock_job
from app.modules.scheduling.adapters.persistence.models import ScheduleCursorModel
from app.modules.scheduling.domain.errors import UnknownJobError
from app.modules.scheduling.domain.schedule_cursor import ScheduleCursor

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: ScheduleCursorModel) -> ScheduleCursor:
    return ScheduleCursor(
        job_key=model.job_key,
        expression=model.expression,
        timezone=model.timezone,
        checked_until=model.checked_until,
    )


class SqlAlchemyScheduleCursorStore:
    """Keep observation changes and submissions inside the same transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def observe(
        self, job_key: str, *, expression: str | None, timezone: str, now: datetime
    ) -> ScheduleCursor:
        """Lock through commit, then initialise or reset changed deployment state."""
        await lock_job(self._session, job_key)
        model = await self._session.get(
            ScheduleCursorModel,
            job_key,
            populate_existing=True,
        )
        if model is None:
            cursor = ScheduleCursor(
                job_key=job_key,
                expression=expression,
                timezone=timezone,
                checked_until=now,
            )
            model = ScheduleCursorModel(
                job_key=job_key,
                expression=expression,
                timezone=timezone,
                checked_until=cursor.checked_until,
            )
            self._session.add(model)
        else:
            cursor = _to_domain(model).observe(expression, timezone, now)
            model.expression = cursor.expression
            model.timezone = cursor.timezone
            model.checked_until = cursor.checked_until
        await self._session.flush()
        return cursor

    async def advance(self, job_key: str, now: datetime) -> None:
        """Advance monotonically while holding the same per-job transaction lock."""
        await lock_job(self._session, job_key)
        model = await self._session.get(
            ScheduleCursorModel,
            job_key,
            populate_existing=True,
        )
        if model is None:
            raise UnknownJobError(job_key)
        model.checked_until = _to_domain(model).advance(now).checked_until
        await self._session.flush()
