from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.system.domain.app_info import AppInfo
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.system.ports.app_info_port import AppInfoPort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetVersionQuery:
    """Request for the running instance's version and build metadata."""


class GetVersion(UseCase[GetVersionQuery, AppInfo]):
    """Report the project version and build provenance of the running instance."""

    def __init__(self, app_info: AppInfoPort) -> None:
        self._app_info = app_info

    async def handle(self, query: GetVersionQuery, actor: Actor) -> AppInfo:
        """Return the current application's version and build metadata."""
        return await self._app_info.load()
