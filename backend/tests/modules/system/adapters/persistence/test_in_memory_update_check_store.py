from datetime import UTC, datetime

from app.modules.system.adapters.persistence.in_memory_update_check_store import (
    InMemoryUpdateCheckStore,
)
from app.modules.system.domain.release import ReleaseChannel, UpdateCheck


async def test_a_saved_result_is_read_back_and_replaced() -> None:
    """A saved result is read back and replaced."""
    store = InMemoryUpdateCheckStore()
    now = datetime(2026, 10, 29, tzinfo=UTC)
    first = UpdateCheck(
        source="o/r",
        channel=ReleaseChannel.STABLE,
        latest=None,
        last_success_at=None,
        last_attempt_at=now,
    )

    assert await store.get("k") is None
    await store.save("k", first)
    assert await store.get("k") is first
    second = first.succeeded(latest=None, at=now)
    await store.save("k", second)
    assert await store.get("k") is second
