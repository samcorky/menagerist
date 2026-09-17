from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.system.domain.app_info import AppInfo


class InMemoryAppInfoAdapter:
    """Fixed-info `AppInfoPort` for tests — no packaged build required."""

    def __init__(self, app_info: AppInfo) -> None:
        self._app_info = app_info

    async def load(self) -> AppInfo:
        """Return the app info this adapter was configured with."""
        return self._app_info
