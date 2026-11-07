import asyncio
import json
import os
import time
from typing import TYPE_CHECKING

from app.shared_kernel.progress import ProgressSnapshot

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import timedelta
    from pathlib import Path

PROGRESS_DIRECTORY = ".progress"


def encode(snapshot: ProgressSnapshot) -> bytes:
    """Serialise a snapshot; it holds only counts, labels and a short message."""
    return json.dumps(snapshot.to_dict(), separators=(",", ":")).encode()


def decode(data: bytes) -> ProgressSnapshot | None:
    """Rebuild a snapshot, or None if the file is not one this code wrote."""
    try:
        return ProgressSnapshot.from_dict(json.loads(data))
    except ValueError, KeyError, TypeError, UnicodeError:
        return None


class LocalProgressStore:
    """One operation's snapshot as a JSON file under `<backup path>/.progress/`.

    The directory sits beside `instance/`, `users/` and `.staging/`, which no
    backup scan visits, and outside the database a restore replaces. Writes are
    atomic (temporary file, then rename), and the file's modification time is
    what ages a snapshot out.
    """

    def __init__(
        self,
        root: Path,
        operation: str,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._directory = root / PROGRESS_DIRECTORY
        self._path = self._directory / f"{operation}.json"
        self._clock = clock

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Replace the file in one rename so a reader never sees half a snapshot."""
        await asyncio.to_thread(self._write, encode(snapshot))

    def _write(self, data: bytes) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, self._path)

    async def read(self, *, max_age: timedelta) -> ProgressSnapshot | None:
        """Return the snapshot unless it is missing, unreadable or too old."""
        return await asyncio.to_thread(self._read, max_age.total_seconds())

    def _read(self, max_age: float) -> ProgressSnapshot | None:
        try:
            age = self._clock() - self._path.stat().st_mtime
            if age > max_age:
                return None
            return decode(self._path.read_bytes())
        except OSError:
            return None
