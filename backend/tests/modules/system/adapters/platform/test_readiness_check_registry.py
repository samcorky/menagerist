from datetime import UTC, datetime

from app.modules.system.adapters.platform.readiness_check_registry import (
    ReadinessCheckRegistry,
)
from app.modules.system.domain.readiness import CheckObservation, CheckStatus


def _observation(status: CheckStatus) -> CheckObservation:
    return CheckObservation(
        component_type="datastore",
        observed_value=1,
        observed_unit="ms",
        status=status,
        time=datetime.now(UTC),
    )


class _FakeCheck:
    def __init__(self, result: dict[str, CheckObservation]) -> None:
        self._result = result

    async def run(self) -> dict[str, CheckObservation]:
        return self._result


async def test_registry_merges_observations_from_multiple_checks() -> None:
    """Each check's observations land under their own key in the merged report."""
    registry = ReadinessCheckRegistry(
        [
            _FakeCheck({"database:responseTime": _observation(CheckStatus.PASS)}),
            _FakeCheck({"database:migrationRevision": _observation(CheckStatus.PASS)}),
        ]
    )

    report = await registry.check()

    assert set(report.checks) == {"database:responseTime", "database:migrationRevision"}
    assert len(report.checks["database:responseTime"]) == 1


async def test_registry_groups_multiple_observations_under_the_same_key() -> None:
    """Two checks reporting the same key produce a list with both observations."""
    registry = ReadinessCheckRegistry(
        [
            _FakeCheck({"database:responseTime": _observation(CheckStatus.PASS)}),
            _FakeCheck({"database:responseTime": _observation(CheckStatus.WARN)}),
        ]
    )

    report = await registry.check()

    assert len(report.checks["database:responseTime"]) == 2


async def test_registry_status_is_worst_of_all_observations() -> None:
    """Overall status is fail if any observation fails, else warn, else pass."""
    fail_registry = ReadinessCheckRegistry(
        [
            _FakeCheck({"a": _observation(CheckStatus.PASS)}),
            _FakeCheck({"b": _observation(CheckStatus.WARN)}),
            _FakeCheck({"c": _observation(CheckStatus.FAIL)}),
        ]
    )
    warn_registry = ReadinessCheckRegistry(
        [
            _FakeCheck({"a": _observation(CheckStatus.PASS)}),
            _FakeCheck({"b": _observation(CheckStatus.WARN)}),
        ]
    )
    pass_registry = ReadinessCheckRegistry(
        [_FakeCheck({"a": _observation(CheckStatus.PASS)})]
    )

    assert (await fail_registry.check()).status is CheckStatus.FAIL
    assert (await warn_registry.check()).status is CheckStatus.WARN
    assert (await pass_registry.check()).status is CheckStatus.PASS


async def test_registry_with_no_checks_passes() -> None:
    """An empty registry has nothing to fail on and reports pass."""
    report = await ReadinessCheckRegistry([]).check()

    assert report.status is CheckStatus.PASS
    assert report.checks == {}
