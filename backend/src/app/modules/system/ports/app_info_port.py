from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.system.domain.app_info import AppInfo


class AppInfoPort(Protocol):
    """Access to the running instance's version and build metadata."""

    async def load(self) -> AppInfo:
        """Return the current application's version and build provenance."""
        ...
