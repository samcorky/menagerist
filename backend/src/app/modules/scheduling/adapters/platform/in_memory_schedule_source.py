"""In-memory effective schedules for scheduler tests and local composition."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class InMemoryScheduleSource:
    """A mutable schedule source with the same off and unknown-key semantics."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self.values = dict(values)

    async def schedule_for(self, schedule_key: str) -> str | None:
        """Return the current expression, or None for an empty value."""
        return self.values[schedule_key] or None
