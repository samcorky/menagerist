from functools import lru_cache
from importlib.metadata import metadata as pkg_metadata

from pydantic import BaseModel

from . import _DISTRIBUTION_NAME


class ProjectInfo(BaseModel):
    """Static project metadata read from the installed package metadata."""

    name: str = _DISTRIBUTION_NAME
    description: str | None = None
    version: str | None = None
    license: str | None = None


@lru_cache(maxsize=1)
def load_project_info() -> ProjectInfo:
    """Load project metadata from the installed package distribution."""
    meta = pkg_metadata(_DISTRIBUTION_NAME)
    return ProjectInfo(
        name=meta.get("Name") or _DISTRIBUTION_NAME,
        description=meta.get("Summary"),
        version=meta.get("Version"),
        license=meta.get("License-Expression") or meta.get("License"),
    )
