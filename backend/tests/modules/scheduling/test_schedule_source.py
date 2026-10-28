"""The schedule-source contract holds for the in-memory and reader-backed sources."""

from typing import TYPE_CHECKING

import pytest

from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.adapters.platform.reader_schedule_source import (
    ReaderScheduleSource,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.scheduling.ports.schedule_source import ScheduleSource
    from app.shared_kernel.settings import SettingKey


class FakeReader:
    """Answers each live key from a dictionary, as the settings reader would."""

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    async def get[T](self, key: SettingKey[T], *, user_id: object = None) -> T:
        """Return the stored value for a key."""
        return self.values[key.key]  # type: ignore[return-value]


def _in_memory() -> ScheduleSource:
    return InMemoryScheduleSource({"backup.schedule": "0 3 * * *", "disabled": ""})


def _reader_backed() -> ScheduleSource:
    return ReaderScheduleSource(
        FakeReader({"backup.schedule": "0 3 * * *", "also.live": ""}),
        live={"backup.schedule", "also.live"},
        static={"disabled": ""},
    )


@pytest.mark.parametrize("make", [_in_memory, _reader_backed])
async def test_schedule_source_contract(make: Callable[[], ScheduleSource]) -> None:
    """Return expressions, treat empty as off and reject unknown schedule keys."""
    source = make()
    assert await source.schedule_for("backup.schedule") == "0 3 * * *"
    assert await source.schedule_for("disabled") is None
    with pytest.raises(KeyError):
        await source.schedule_for("unknown")


async def test_a_live_schedule_follows_the_reader_on_every_call() -> None:
    """A change made through settings is seen without rebuilding the source."""
    reader = FakeReader({"backup.schedule": "0 3 * * *"})
    source = ReaderScheduleSource(reader, live={"backup.schedule"}, static={})
    assert await source.schedule_for("backup.schedule") == "0 3 * * *"
    reader.values["backup.schedule"] = "0 4 * * *"
    assert await source.schedule_for("backup.schedule") == "0 4 * * *"
    reader.values["backup.schedule"] = ""
    assert await source.schedule_for("backup.schedule") is None


async def test_a_static_schedule_ignores_the_reader() -> None:
    """Schedules that are not live never reach the settings reader."""

    class Boom:
        async def get(self, key: object, *, user_id: object = None) -> str:
            raise AssertionError("must not read settings")

    source = ReaderScheduleSource(Boom(), live=set(), static={"fixed": "0 5 * * *"})  # type: ignore[arg-type]
    assert await source.schedule_for("fixed") == "0 5 * * *"
