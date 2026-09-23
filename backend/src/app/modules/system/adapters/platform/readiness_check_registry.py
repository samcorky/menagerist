import asyncio
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

    Checks run concurrently; their observations are merged (grouped by key) and
    the aggregate status is the worst of any individual observation.
    """

    def __init__(self, checks: Sequence[ReadinessCheck]) -> None:
        self._checks = checks

    async def check(self) -> ReadinessReport:
        """Run all registered checks and return their aggregate result."""
        results = await asyncio.gather(*(check.run() for check in self._checks))

        checks: dict[str, list[CheckObservation]] = {}
        for result in results:
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
