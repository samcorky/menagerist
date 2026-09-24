from functools import lru_cache
from pathlib import Path  # noqa: TC003 - pydantic resolves the annotation at runtime

from pydantic import Field

from app.platform.config._base import CSV, MenageristBaseSettings


class ApiSettings(MenageristBaseSettings):
    """API entrypoint settings."""

    cors_origins: CSV[str] = Field(default=["*"])
    # When set, the API process also serves the built web UI from this
    # directory; when unset it is API-only (development, split deployments).
    frontend_dist_path: Path | None = None


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Return the cached API settings."""
    return ApiSettings()
