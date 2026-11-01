from datetime import UTC, datetime
from unittest.mock import patch

from app.modules.system.adapters.platform.app_info_adapter import PackageAppInfoAdapter
from app.platform.app_info import AppInfo as PlatformAppInfo
from app.platform.build_info import BuildInfo
from app.platform.project_info import ProjectInfo

_PATCH_LOAD_APP_INFO = (
    "app.modules.system.adapters.platform.app_info_adapter.load_app_info"
)
_PATCH_CODE_HEAD_REVISIONS = (
    "app.modules.system.adapters.platform.app_info_adapter.code_head_revisions"
)


async def test_load_maps_platform_app_info_to_domain_app_info() -> None:
    """PackageAppInfoAdapter maps platform AppInfo + Alembic heads to the domain."""
    build_timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    platform_app_info = PlatformAppInfo(
        project=ProjectInfo(name="menagerist", version="1.2.3", license="Apache-2.0"),
        build=BuildInfo(
            commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            short_sha="a1b2c3d",
            branch="main",
            dirty=False,
            build_timestamp=build_timestamp,
        ),
    )
    adapter = PackageAppInfoAdapter()

    with (
        patch(_PATCH_LOAD_APP_INFO, return_value=platform_app_info),
        patch(_PATCH_CODE_HEAD_REVISIONS, return_value=("abc123",)),
    ):
        app_info = await adapter.load()

    assert app_info.name == "menagerist"
    assert app_info.version == "1.2.3"
    assert app_info.commit_sha == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    assert app_info.short_sha == "a1b2c3d"
    assert app_info.branch == "main"
    assert app_info.dirty is False
    assert app_info.build_timestamp == build_timestamp
    assert app_info.migration_head == ("abc123",)
