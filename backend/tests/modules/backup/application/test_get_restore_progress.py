"""The first-run page reads a restore's progress without an account."""

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.backup.adapters.storage.in_memory_progress_store import (
    InMemoryProgressStore,
)
from app.modules.backup.application.get_restore_progress import (
    RESTORE_PROGRESS_MAX_AGE,
    GetRestoreProgress,
    GetRestoreProgressQuery,
)
from app.modules.backup.domain.errors import RestoreProgressNotFoundError
from app.shared_kernel.actor import ANONYMOUS_ACTOR
from app.shared_kernel.progress import ProgressSnapshot

SNAPSHOT = ProgressSnapshot(phases=(), message=None, percent=50, outcome="running")


class Clock:
    """A hand-wound clock in seconds."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        """Read the clock."""
        return self.now


async def test_an_anonymous_caller_gets_the_stored_snapshot() -> None:
    """The page has no account yet, so the query is public."""
    store = InMemoryProgressStore()
    await store.write(SNAPSHOT)
    result = await GetRestoreProgress(store, get_access_guard()).handle(
        GetRestoreProgressQuery(), ANONYMOUS_ACTOR
    )
    assert result is SNAPSHOT


async def test_no_snapshot_is_not_found() -> None:
    """Nothing reported means there is nothing to show."""
    with pytest.raises(RestoreProgressNotFoundError):
        await GetRestoreProgress(InMemoryProgressStore(), get_access_guard()).handle(
            GetRestoreProgressQuery(), ANONYMOUS_ACTOR
        )


async def test_an_expired_snapshot_is_not_found() -> None:
    """A finished restore stays readable for a few minutes, then goes."""
    clock = Clock()
    store = InMemoryProgressStore(clock=clock)
    await store.write(SNAPSHOT)
    clock.now = RESTORE_PROGRESS_MAX_AGE.total_seconds() + 1
    with pytest.raises(RestoreProgressNotFoundError):
        await GetRestoreProgress(store, get_access_guard()).handle(
            GetRestoreProgressQuery(), ANONYMOUS_ACTOR
        )
