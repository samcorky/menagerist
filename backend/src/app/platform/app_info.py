from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel

from app.platform.build_info import BuildInfo, load_build_info
from app.platform.project_info import ProjectInfo, load_project_info


class AppInfo(BaseModel):
    """Public application metadata composed from project and build information."""

    project: ProjectInfo
    build: BuildInfo

    @property
    def name(self) -> str:
        """Return the application package name."""
        return self.project.name

    @property
    def version(self) -> str | None:
        """Return the application package version."""
        return self.project.version


@lru_cache(maxsize=1)
def load_app_info() -> AppInfo:
    """Load public application metadata."""
    return AppInfo(
        project=load_project_info(),
        build=load_build_info(),
    )
