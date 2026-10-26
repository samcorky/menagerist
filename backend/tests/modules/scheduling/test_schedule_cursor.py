"""Cursor state is independent of job history and advances monotonically."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.scheduling.adapters.persistence.in_memory_schedule_cursor_store import (  # noqa: E501
    InMemoryScheduleCursorStore,
)
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.domain.errors import UnknownJobError

NOW = datetime(2026, 10, 26, 3, tzinfo=UTC)


async def test_cursor_store_requires_observation_before_advance() -> None:
    """An advance cannot silently invent an unknown job's observation state."""
    cursors = InMemoryScheduleCursorStore(InMemorySchedulingStore())
    with pytest.raises(UnknownJobError):
        await cursors.advance("missing", NOW)
    first = await cursors.observe("x", expression="* * * * *", timezone="UTC", now=NOW)
    await cursors.advance("x", NOW - timedelta(minutes=1))
    observed = await cursors.observe(
        "x", expression="* * * * *", timezone="UTC", now=NOW
    )
    assert observed.checked_until == first.checked_until == NOW
