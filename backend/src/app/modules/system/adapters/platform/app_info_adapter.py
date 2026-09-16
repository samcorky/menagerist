from app.modules.system.domain.app_info import AppInfo
from app.platform.alembic_runner import code_head_revisions
from app.platform.app_info import load_app_info


class PackageAppInfoAdapter:
    """Reads version and build metadata from the installed package."""

    async def load(self) -> AppInfo:
        """Return version and build metadata sourced from platform package info."""
        app_info = load_app_info()
        build = app_info.build
        return AppInfo(
            name=app_info.name,
            version=app_info.version,
            commit_sha=build.commit_sha,
            short_sha=build.short_sha,
            branch=build.branch,
            dirty=build.dirty,
            build_timestamp=build.build_timestamp,
            migration_head=code_head_revisions(),
        )
