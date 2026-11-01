from functools import lru_cache

from pydantic import BaseModel

from app.platform.build_info import BuildInfo, load_build_info
from app.platform.project_info import ProjectInfo, load_project_info


class AppInfo(BaseModel):
    """Public application metadata composed of project and build information."""

    project: ProjectInfo
    build: BuildInfo

    @property
    def name(self) -> str:
        """Return the application package name."""
        return self.project.name

    @property
    def version(self) -> str:
        """Return the application package version."""
        return self.project.version

    @property
    def license_url(self) -> str | None:
        """Return the application license URL if repository metadata is available."""
        if not self.build.repository_url:
            return None

        base_url = self.build.repository_url.rstrip("/")
        if self.build.commit_sha:
            return f"{base_url}/blob/{self.build.commit_sha}/LICENSE"
        return f"{base_url}/blob/main/LICENSE"


@lru_cache(maxsize=1)
def load_app_info() -> AppInfo:
    """Load public application metadata."""
    return AppInfo(
        project=load_project_info(),
        build=load_build_info(),
    )
