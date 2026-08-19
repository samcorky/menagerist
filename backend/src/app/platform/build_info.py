from __future__ import annotations

from functools import lru_cache
from importlib.metadata import distribution
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.platform import _DISTRIBUTION_NAME

if TYPE_CHECKING:
    from datetime import datetime


class BuildInfo(BaseModel):
    """Build and source-control metadata captured when the package was built."""

    commit_sha: str | None = None
    short_sha: str | None = None
    branch: str | None = None
    dirty: bool | None = None
    repository_url: str | None = None
    build_timestamp: datetime | None = None


@lru_cache(maxsize=1)
def load_build_info() -> BuildInfo:
    """Load build metadata embedded in the installed package."""
    raw = distribution(_DISTRIBUTION_NAME).read_text("extra_metadata/build_info.json")
    return BuildInfo() if raw is None else BuildInfo.model_validate_json(raw)
