from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.readiness import ReadinessReport
from app.modules.system.ports.health_check_port import HealthCheckPort
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.guarded import GuardedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetHealthReadyDetailQuery:
    """Request for the full readiness report."""


class GetHealthReadyDetail(
    GuardedQueryHandler[HealthCheckPort, GetHealthReadyDetailQuery, ReadinessReport]
):
    """Report every readiness check with its observed values, for administrators."""

    access: ClassVar[Access] = Requires(SystemPermission.READ_DIAGNOSTICS)

    async def _handle(
        self, query: GetHealthReadyDetailQuery, actor: Actor
    ) -> ReadinessReport:
        """Run the checks and return the full report."""
        return await self._repos.check()
