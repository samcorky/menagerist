"""Schedules that an administrator may change, resolved through the settings reader."""

from typing import TYPE_CHECKING

from app.shared_kernel.settings import SettingKey

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from app.shared_kernel.settings import SettingsReader


class ReaderScheduleSource:
    """Answer live schedule keys from the reader and the rest from a fixed snapshot.

    A live key names a tunable setting, so the answer follows the deployment pin, then
    the administrator's value, then the default, and is re-read on every tick. The
    other keys are deployment values that nothing edits at runtime.
    """

    def __init__(
        self,
        reader: SettingsReader,
        *,
        live: Collection[str],
        static: Mapping[str, str],
    ) -> None:
        self._reader = reader
        self._live = frozenset(live)
        self._static = dict(static)

    async def schedule_for(self, schedule_key: str) -> str | None:
        """Return a cron expression; an empty value turns the job off."""
        if schedule_key in self._live:
            return await self._reader.get(SettingKey[str](schedule_key)) or None
        return self._static[schedule_key] or None
