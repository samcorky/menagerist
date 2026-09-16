from app.modules.system.application.get_version import GetVersion, GetVersionQuery
from app.modules.system.domain.app_info import AppInfo
from app.shared_kernel.actor import SYSTEM_ACTOR


class _StubAppInfo:
    def __init__(self, app_info: AppInfo) -> None:
        self._app_info = app_info

    async def load(self) -> AppInfo:
        return self._app_info


async def test_get_version_delegates_to_app_info_port() -> None:
    """GetVersion returns the app info produced by the app info port."""
    app_info = AppInfo(name="menagerist", version="1.2.3", migration_head=("abc123",))
    use_case = GetVersion(_StubAppInfo(app_info))

    result = await use_case.handle(GetVersionQuery(), SYSTEM_ACTOR)

    assert result is app_info
