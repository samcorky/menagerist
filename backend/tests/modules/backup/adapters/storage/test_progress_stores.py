"""Progress stores keep one operation's latest snapshot, readable until it ages out."""

import os
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.backup.adapters.storage.in_memory_progress_store import (
    InMemoryProgressStore,
)
from app.modules.backup.adapters.storage.local_progress_store import (
    PROGRESS_DIRECTORY,
    LocalProgressStore,
    decode,
    encode,
)
from app.shared_kernel.progress import PhaseState, ProgressSnapshot

if TYPE_CHECKING:
    from pathlib import Path

SNAPSHOT = ProgressSnapshot(
    phases=(
        PhaseState(key="verify", label="Checking", state="done", done=9, total=9),
        PhaseState(
            key="media",
            label="Restoring photos",
            state="running",
            done=3,
            total=10,
            unit="count",
        ),
    ),
    message="Almost there",
    percent=40,
    outcome="running",
)
MAX_AGE = timedelta(minutes=10)


class Clock:
    """A hand-wound clock in seconds."""

    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        """Read the clock."""
        return self.now


def test_a_snapshot_survives_a_round_trip_through_json() -> None:
    """Everything a viewer needs is in the file."""
    assert decode(encode(SNAPSHOT)) == SNAPSHOT


@pytest.mark.parametrize(
    "data",
    [b"", b"not json", b"[]", b"{}", b'{"phases": [{"nope": 1}]}', b"\xff\xfe"],
)
def test_a_file_this_code_did_not_write_is_ignored(data: bytes) -> None:
    """Anything malformed reads as no snapshot, never as an error."""
    assert decode(data) is None


async def test_the_local_store_writes_under_the_progress_directory(
    tmp_path: Path,
) -> None:
    """The file sits beside instance/ and users/, named for its operation."""
    store = LocalProgressStore(tmp_path, "restore")
    await store.write(SNAPSHOT)
    assert (tmp_path / PROGRESS_DIRECTORY / "restore.json").is_file()
    assert await store.read(max_age=MAX_AGE) == SNAPSHOT


async def test_a_write_replaces_the_previous_snapshot_and_leaves_no_temp_file(
    tmp_path: Path,
) -> None:
    """Only the latest snapshot remains."""
    store = LocalProgressStore(tmp_path, "restore")
    await store.write(SNAPSHOT)
    done = ProgressSnapshot(phases=(), message=None, percent=100, outcome="succeeded")
    await store.write(done)
    assert await store.read(max_age=MAX_AGE) == done
    assert [p.name for p in (tmp_path / PROGRESS_DIRECTORY).iterdir()] == [
        "restore.json"
    ]


async def test_operations_do_not_share_a_file(tmp_path: Path) -> None:
    """Each operation key has its own snapshot."""
    await LocalProgressStore(tmp_path, "restore").write(SNAPSHOT)
    assert await LocalProgressStore(tmp_path, "verify").read(max_age=MAX_AGE) is None


async def test_a_missing_file_reads_as_nothing(tmp_path: Path) -> None:
    """Before any write there is no snapshot."""
    assert await LocalProgressStore(tmp_path, "restore").read(max_age=MAX_AGE) is None


async def test_a_snapshot_ages_out_from_its_last_write(tmp_path: Path) -> None:
    """A stale snapshot is not served, and a fresh write revives the file."""
    store = LocalProgressStore(tmp_path, "restore")
    await store.write(SNAPSHOT)
    path = tmp_path / PROGRESS_DIRECTORY / "restore.json"
    modified = path.stat().st_mtime
    fresh = LocalProgressStore(tmp_path, "restore", clock=Clock(modified + 599))
    stale = LocalProgressStore(tmp_path, "restore", clock=Clock(modified + 601))
    assert await fresh.read(max_age=MAX_AGE) == SNAPSHOT
    assert await stale.read(max_age=MAX_AGE) is None
    os.utime(path, (modified + 600, modified + 600))
    assert await stale.read(max_age=MAX_AGE) == SNAPSHOT


async def test_a_corrupt_file_reads_as_nothing(tmp_path: Path) -> None:
    """A half-written or foreign file never raises into the request."""
    store = LocalProgressStore(tmp_path, "restore")
    await store.write(SNAPSHOT)
    (tmp_path / PROGRESS_DIRECTORY / "restore.json").write_bytes(b"{")
    assert await store.read(max_age=MAX_AGE) is None


async def test_the_in_memory_store_mirrors_the_local_one() -> None:
    """The fast-test sibling has the same read and age-out behaviour."""
    clock = Clock(1000.0)
    store = InMemoryProgressStore(clock=clock)
    assert await store.read(max_age=MAX_AGE) is None
    await store.write(SNAPSHOT)
    clock.now = 1599.0
    assert await store.read(max_age=MAX_AGE) == SNAPSHOT
    clock.now = 1601.0
    assert await store.read(max_age=MAX_AGE) is None
