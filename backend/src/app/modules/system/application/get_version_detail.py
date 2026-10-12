from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.app_info import AppInfo
from app.modules.system.ports.app_info_port import AppInfoPort
from app.shared_kernel.cqrs import AuthorisedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetVersionDetailQuery:
    """Request for the full build provenance of the running instance."""


class GetVersionDetail(
    AuthorisedQueryHandler[
        AppInfoPort, GetVersionDetailQuery, AppInfo, SystemPermission
    ]
):
    """Report commit, branch and migration head, for administrators."""

    required_permission = SystemPermission.READ_DIAGNOSTICS

    async def _handle(self, query: GetVersionDetailQuery, actor: Actor) -> AppInfo:
        """Return the application's version and full build metadata."""
        return await self._repos.load()
