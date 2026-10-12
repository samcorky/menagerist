from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.readiness import ReadinessReport
from app.modules.system.ports.health_check_port import HealthCheckPort
from app.shared_kernel.cqrs import AuthorisedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetHealthReadyDetailQuery:
    """Request for the full readiness report."""


class GetHealthReadyDetail(
    AuthorisedQueryHandler[
        HealthCheckPort, GetHealthReadyDetailQuery, ReadinessReport, SystemPermission
    ]
):
    """Report every readiness check with its observed values, for administrators."""

    required_permission = SystemPermission.READ_DIAGNOSTICS

    async def _handle(
        self, query: GetHealthReadyDetailQuery, actor: Actor
    ) -> ReadinessReport:
        """Run the checks and return the full report."""
        return await self._repos.check()
