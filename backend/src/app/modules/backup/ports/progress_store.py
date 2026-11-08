from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import timedelta

    from app.shared_kernel.progress import ProgressSnapshot


class ProgressStore(Protocol):
    """The latest progress of one operation, kept outside the database.

    Restores replace the tables a progress row would live in, so this is a
    sink that can also be read back. It satisfies `ProgressSink` structurally.
    """

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Replace the stored snapshot atomically."""
        ...

    async def read(self, *, max_age: timedelta) -> ProgressSnapshot | None:
        """Return the snapshot, or None if absent or older than `max_age`."""
        ...
