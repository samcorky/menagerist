from app.modules.system.adapters.platform.in_memory_app_info_adapter import (
    InMemoryAppInfoAdapter,
)
from app.modules.system.application.get_version import GetVersion, GetVersionQuery
from app.modules.system.domain.app_info import AppInfo
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_get_version_delegates_to_app_info_port() -> None:
    """GetVersion returns the app info produced by the app info port."""
    app_info = AppInfo(name="menagerist", version="1.2.3", migration_head=("abc123",))
    use_case = GetVersion(InMemoryAppInfoAdapter(app_info))

    result = await use_case.handle(GetVersionQuery(), SYSTEM_ACTOR)

    assert result is app_info
