from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.system.domain.readiness import ReadinessReport


class InMemoryHealthCheckAdapter:
    """Fixed-report `HealthCheckPort` for tests — no database required."""

    def __init__(self, report: ReadinessReport) -> None:
        self._report = report

    async def check(self) -> ReadinessReport:
        """Return the report this adapter was configured with."""
        return self._report
