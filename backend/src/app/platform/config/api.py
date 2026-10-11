from functools import lru_cache
from pathlib import Path  # noqa: TC003 - pydantic resolves the annotation at runtime

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._types import (  # noqa: TC001 - pydantic resolves these at runtime
    Origin,
    ProxyAddress,
    StarOrCSV,
)


class ApiSettings(MenageristBaseSettings):
    """API entrypoint settings."""

    cors_origins: StarOrCSV[Origin] = Field(default=["*"])

    # When set, the API process also serves the built web UI from this
    # directory; when unset it is API-only (development, split deployments).
    frontend_dist_path: Path | None = None

    # Peers whose X-Forwarded-For / -Proto headers are believed: addresses,
    # networks (CIDR) or "*" for any peer. Others are seen as their socket
    # address, so a direct client cannot spoof the address the throttle uses.
    trusted_proxies: StarOrCSV[ProxyAddress] = Field(default=["127.0.0.1"])


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Return the cached API settings."""
    return ApiSettings()
