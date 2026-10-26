"""Schedule snapshots supplied by deployment settings at the composition root."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class SettingsScheduleSource:
    """Read a snapshot of module settings without importing their modules."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)

    async def schedule_for(self, schedule_key: str) -> str | None:
        """Return an expression; an explicitly empty setting disables the job."""
        return self._values[schedule_key] or None
