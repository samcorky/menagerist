from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.system.domain.app_info import AppInfo
from app.shared_kernel.access import Access, Public
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001
from app.shared_kernel.guarded import GuardedUseCase

if TYPE_CHECKING:
    from app.modules.system.ports.app_info_port import AppInfoPort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetVersionQuery:
    """Request for the running instance's version and build metadata."""


class GetVersion(GuardedUseCase[GetVersionQuery, AppInfo]):
    """Report the project version and build provenance of the running instance."""

    access: ClassVar[Access] = Public()

    def __init__(self, app_info: AppInfoPort, guard: AccessGuard) -> None:
        self._app_info = app_info
        self._guard = guard

    async def _handle(self, query: GetVersionQuery, actor: Actor) -> AppInfo:
        """Return the current application's version and build metadata."""
        return await self._app_info.load()
