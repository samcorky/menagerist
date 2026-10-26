"""The schedule-source contract is independent of layered settings."""

from typing import TYPE_CHECKING

import pytest

from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.adapters.platform.settings_schedule_source import (
    SettingsScheduleSource,
)

if TYPE_CHECKING:
    from app.modules.scheduling.ports.schedule_source import ScheduleSource


@pytest.mark.parametrize(
    "source_type", [SettingsScheduleSource, InMemoryScheduleSource]
)
async def test_schedule_source_contract(
    source_type: type[SettingsScheduleSource] | type[InMemoryScheduleSource],
) -> None:
    """Return expressions, treat empty as off and reject unknown schedule keys."""
    source: ScheduleSource = source_type(
        {"backup.schedule": "0 3 * * *", "disabled": ""}
    )
    assert await source.schedule_for("backup.schedule") == "0 3 * * *"
    assert await source.schedule_for("disabled") is None
    with pytest.raises(KeyError):
        await source.schedule_for("unknown")
