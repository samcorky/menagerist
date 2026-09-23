from typing import TYPE_CHECKING

from app.modules.system.domain.readiness import (
    CheckObservation,
    CheckStatus,
    ReadinessReport,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.system.ports.readiness_check import ReadinessCheck


class ReadinessCheckRegistry:
    """`HealthCheckPort` adapter that runs a set of pluggable `ReadinessCheck`s.

    Checks run sequentially, in registration order — not concurrently. Some
    checks observe shared, mutable state (e.g. connection-pool utilisation) that
    other checks affect while they run (they hold a pooled connection open for
    their query); running everything concurrently would make those readings
    reflect the probe's own in-flight load rather than a settled baseline.
    Their observations are merged (grouped by key) and the aggregate status is
    the worst of any individual observation.
    """

    def __init__(self, checks: Sequence[ReadinessCheck]) -> None:
        self._checks = checks

    async def check(self) -> ReadinessReport:
        """Run all registered checks and return their aggregate result."""
        checks: dict[str, list[CheckObservation]] = {}
        for readiness_check in self._checks:
            result = await readiness_check.run()
            for key, observation in result.items():
                checks.setdefault(key, []).append(observation)

        all_observations = [
            obs for observations in checks.values() for obs in observations
        ]
        if any(obs.status is CheckStatus.FAIL for obs in all_observations):
            overall = CheckStatus.FAIL
        elif any(obs.status is CheckStatus.WARN for obs in all_observations):
            overall = CheckStatus.WARN
        else:
            overall = CheckStatus.PASS
        return ReadinessReport(status=overall, checks=checks)
