from functools import lru_cache
from importlib.metadata import metadata as pkg_metadata

from pydantic import BaseModel

from . import _DISTRIBUTION_NAME


class ProjectInfo(BaseModel):
    """Static project metadata read from the installed package metadata."""

    name: str
    description: str | None = None
    version: str
    license: str | None = None


@lru_cache(maxsize=1)
def load_project_info() -> ProjectInfo:
    """Load project metadata from the installed package distribution."""
    meta = pkg_metadata(_DISTRIBUTION_NAME)
    version = meta.get("Version")
    if version is None:
        raise RuntimeError(
            f"Package {_DISTRIBUTION_NAME!r} is missing required Version metadata"
        )
    return ProjectInfo(
        name=meta.get("Name") or _DISTRIBUTION_NAME,
        description=meta.get("Summary"),
        version=version,
        license=meta.get("License-Expression") or meta.get("License"),
    )
