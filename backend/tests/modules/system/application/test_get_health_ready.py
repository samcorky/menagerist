from datetime import UTC, datetime

from app.modules.system.application.get_health_ready import (
    GetHealthReady,
    GetHealthReadyQuery,
)
from app.modules.system.domain.readiness import (
    CheckObservation,
    CheckStatus,
    ReadinessReport,
)
from app.shared_kernel.actor import SYSTEM_ACTOR


class _StubHealthCheck:
    def __init__(self, report: ReadinessReport) -> None:
        self._report = report

    async def check(self) -> ReadinessReport:
        return self._report


async def test_get_health_ready_delegates_to_health_check_port() -> None:
    """GetHealthReady returns the report produced by the health check port."""
    report = ReadinessReport(
        status=CheckStatus.PASS,
        checks={
            "database:responseTime": CheckObservation(
                component_type="datastore",
                observed_value=1.23,
                observed_unit="ms",
                status=CheckStatus.PASS,
                time=datetime.now(UTC),
            )
        },
    )
    use_case = GetHealthReady(_StubHealthCheck(report))

    result = await use_case.handle(GetHealthReadyQuery(), SYSTEM_ACTOR)

    assert result is report
