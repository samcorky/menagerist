import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import timedelta

    from app.shared_kernel.progress import ProgressSnapshot


class InMemoryProgressStore:
    """Holds the latest snapshot and when it was written, for fast tests."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self.snapshot: ProgressSnapshot | None = None
        self.written_at = 0.0

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Keep the snapshot."""
        self.snapshot = snapshot
        self.written_at = self._clock()

    async def read(self, *, max_age: timedelta) -> ProgressSnapshot | None:
        """Return the snapshot unless it is missing or older than `max_age`."""
        if self.snapshot is None:
            return None
        if self._clock() - self.written_at > max_age.total_seconds():
            return None
        return self.snapshot
