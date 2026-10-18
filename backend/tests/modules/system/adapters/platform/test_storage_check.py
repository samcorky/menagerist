import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import time_machine

from app.modules.system.adapters.platform.checks.storage_check import StorageCheck
from app.modules.system.domain.readiness import CheckStatus
from app.platform.storage_probe import DirectoryProbe

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 10, 18, 11, tzinfo=UTC)
_GIB = 1024**3


async def test_reports_writable_state_and_free_space(tmp_path: Path) -> None:
    """A usable directory has exactly the two documented observations."""
    check = StorageCheck({"media": tmp_path})

    result = await check.run()

    assert set(result) == {"storage:mediaWritable", "storage:mediaFreeSpace"}
    assert result["storage:mediaWritable"].observed_value == "writable"
    assert result["storage:mediaWritable"].observed_unit == "state"
    assert result["storage:mediaWritable"].status is CheckStatus.PASS
    assert result["storage:mediaFreeSpace"].observed_unit == "GiB"
    assert result["storage:mediaFreeSpace"].status is CheckStatus.PASS


async def test_warns_with_operator_hint_when_not_writable(tmp_path: Path) -> None:
    """A non-writable directory reports a warning and bind-mount guidance."""
    check = StorageCheck({"media": tmp_path})
    probe = DirectoryProbe(state="not-writable", free_bytes=_GIB * 2)
    with patch(
        "app.modules.system.adapters.platform.checks.storage_check.probe_directory",
        return_value=probe,
    ):
        result = await check.run()

    observation = result["storage:mediaWritable"]
    assert observation.status is CheckStatus.WARN
    assert observation.output is not None
    assert "chown 1000:1000" in observation.output


async def test_warns_when_free_space_is_below_threshold(tmp_path: Path) -> None:
    """Low free space warns with the observed value and configured threshold."""
    check = StorageCheck({"media": tmp_path}, min_free_bytes=_GIB)
    with patch("app.platform.storage_probe.shutil.disk_usage") as disk_usage_mock:
        disk_usage_mock.return_value.free = _GIB // 2
        result = await check.run()
        disk_usage_mock.assert_called_once_with(tmp_path)

    observation = result["storage:mediaFreeSpace"]
    assert observation.observed_value == 0.5
    assert observation.status is CheckStatus.WARN
    assert observation.output is not None
    assert "minimum: 1.00 GiB" in observation.output


async def test_omits_free_space_when_directory_is_missing(tmp_path: Path) -> None:
    """Missing directories have a writable-state warning but no space reading."""
    check = StorageCheck({"media": tmp_path / "missing"})

    result = await check.run()

    assert set(result) == {"storage:mediaWritable"}
    assert result["storage:mediaWritable"].observed_value == "missing"
    assert result["storage:mediaWritable"].status is CheckStatus.WARN
    assert result["storage:mediaWritable"].output is not None


@time_machine.travel(NOW, tick=False)
async def test_reuses_probe_until_cache_expires(tmp_path: Path) -> None:
    """Probe results are reused for 60 seconds and refreshed after expiry."""
    check = StorageCheck({"media": tmp_path})
    probe = DirectoryProbe(state="writable", free_bytes=_GIB * 2)
    with patch(
        "app.modules.system.adapters.platform.checks.storage_check.probe_directory",
        return_value=probe,
    ) as probe_mock:
        await check.run()
        await check.run()
        assert probe_mock.call_count == 1

        with time_machine.travel(NOW + timedelta(seconds=61), tick=False):
            await check.run()

    assert probe_mock.call_count == 2


async def test_concurrent_calls_share_one_probe(tmp_path: Path) -> None:
    """Concurrent calls wait on the check lock and share the resulting probe."""
    check = StorageCheck({"media": tmp_path})
    probe = DirectoryProbe(state="writable", free_bytes=_GIB * 2)
    with patch(
        "app.modules.system.adapters.platform.checks.storage_check.probe_directory",
        return_value=probe,
    ) as probe_mock:
        await asyncio.gather(check.run(), check.run(), check.run())

    assert probe_mock.call_count == 1


async def test_rounds_free_space_to_two_decimal_places(tmp_path: Path) -> None:
    """The reported free-space value is rounded to GiB."""
    check = StorageCheck({"media": tmp_path})
    probe = DirectoryProbe(state="writable", free_bytes=3 * _GIB + 456_000_000)
    with patch(
        "app.modules.system.adapters.platform.checks.storage_check.probe_directory",
        return_value=probe,
    ):
        result = await check.run()

    assert result["storage:mediaFreeSpace"].observed_value == 3.42
