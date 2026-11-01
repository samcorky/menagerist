"""In-memory schedule observation state, separate from job-run history."""

from typing import TYPE_CHECKING

from app.modules.scheduling.domain.errors import UnknownJobError
from app.modules.scheduling.domain.schedule_cursor import ScheduleCursor

if TYPE_CHECKING:
    from datetime import datetime

    from app.modules.scheduling.adapters.persistence.in_memory_store import (
        InMemorySchedulingStore,
    )


class InMemoryScheduleCursorStore:
    """Track deployment changes and monotonically advancing observation windows."""

    def __init__(self, store: InMemorySchedulingStore) -> None:
        self._store = store

    async def observe(
        self, job_key: str, *, expression: str | None, timezone: str, now: datetime
    ) -> ScheduleCursor:
        """Initialise a new cursor or apply deployment changes to an existing one."""
        previous = self._store.cursors.get(job_key)
        cursor = (
            ScheduleCursor(
                job_key=job_key,
                expression=expression,
                timezone=timezone,
                checked_until=now,
            )
            if previous is None
            else previous.observe(expression, timezone, now)
        )
        self._store.cursors[job_key] = cursor
        return cursor

    async def advance(self, job_key: str, now: datetime) -> None:
        """Advance a previously observed job without moving its cursor backwards."""
        if job_key not in self._store.cursors:
            raise UnknownJobError(job_key)
        self._store.cursors[job_key] = self._store.cursors[job_key].advance(now)
