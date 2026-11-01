"""Transaction-scoped coordination for schedule observation windows."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from app.modules.scheduling.domain.schedule_cursor import ScheduleCursor


class ScheduleCursorStore(Protocol):
    """Keep observation state separate from prunable run history."""

    async def observe(
        self, job_key: str, *, expression: str | None, timezone: str, now: datetime
    ) -> ScheduleCursor:
        """Lock through commit; initialise or reset a changed schedule at now."""
        ...

    async def advance(self, job_key: str, now: datetime) -> None:
        """Advance an observed job in the same transaction as its submission."""
        ...
