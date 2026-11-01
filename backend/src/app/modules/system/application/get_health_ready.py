from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.system.domain.readiness import ReadinessReport
from app.shared_kernel.access import Access, Public
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.system.ports.health_check_port import HealthCheckPort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetHealthReadyQuery:
    """Request for a readiness check."""


class GetHealthReady(UseCase[GetHealthReadyQuery, ReadinessReport]):
    """Report readiness by verifying all required dependencies are reachable."""

    access: ClassVar[Access] = Public()

    def __init__(self, health_check: HealthCheckPort, guard: AccessGuard) -> None:
        self._health_check = health_check
        self._guard = guard

    async def _handle(
        self, query: GetHealthReadyQuery, actor: Actor
    ) -> ReadinessReport:
        """Delegate to the health check port and return its aggregate report."""
        return await self._health_check.check()
