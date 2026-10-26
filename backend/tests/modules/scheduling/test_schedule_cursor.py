"""Cursor state is independent of job history and advances monotonically."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.scheduling.adapters.persistence.in_memory_schedule_cursor_store import (  # noqa: E501
    InMemoryScheduleCursorStore,
)
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.schedule_cursor_store import (
    SqlAlchemyScheduleCursorStore,
)
from app.modules.scheduling.domain.errors import UnknownJobError

if TYPE_CHECKING:
    from app.modules.scheduling.ports.schedule_cursor_store import ScheduleCursorStore

NOW = datetime(2026, 10, 26, 3, tzinfo=UTC)


@pytest.fixture(
    params=["memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def cursors(request: pytest.FixtureRequest) -> ScheduleCursorStore:
    """Run observation contracts against both storage implementations."""
    if request.param == "memory":
        return InMemoryScheduleCursorStore(InMemorySchedulingStore())
    return SqlAlchemyScheduleCursorStore(request.getfixturevalue("db_session"))


async def test_cursor_store_requires_observation_before_advance(
    cursors: ScheduleCursorStore,
) -> None:
    """An advance cannot silently invent an unknown job's observation state."""
    with pytest.raises(UnknownJobError):
        await cursors.advance("missing", NOW)
    first = await cursors.observe("x", expression="* * * * *", timezone="UTC", now=NOW)
    await cursors.advance("x", NOW - timedelta(minutes=1))
    observed = await cursors.observe(
        "x", expression="* * * * *", timezone="UTC", now=NOW
    )
    assert observed.checked_until == first.checked_until == NOW


async def test_cursor_changes_reset_without_regressing(
    cursors: ScheduleCursorStore,
) -> None:
    """Disabled schedules, timezone changes and clock regressions share one policy."""
    await cursors.observe("x", expression="* * * * *", timezone="UTC", now=NOW)
    later = NOW + timedelta(hours=1)
    await cursors.advance("x", later)
    same = await cursors.observe(
        "x", expression="* * * * *", timezone="UTC", now=later + timedelta(hours=1)
    )
    assert same.checked_until == later
    changed = await cursors.observe(
        "x", expression=None, timezone="Europe/London", now=NOW
    )
    assert changed.checked_until == later
    assert changed.expression is None
    assert changed.timezone == "Europe/London"
    enabled = await cursors.observe(
        "x",
        expression="0 3 * * *",
        timezone="Europe/London",
        now=later + timedelta(hours=2),
    )
    assert enabled.checked_until == later + timedelta(hours=2)
