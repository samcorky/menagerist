from functools import lru_cache
from pathlib import Path  # noqa: TC003 - pydantic resolves the annotation at runtime

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._types import (  # noqa: TC001 - pydantic resolves these at runtime
    Origin,
    ProxyAddress,
    StarOrCSV,
)

CORS_OPEN_HINT = (
    "CORS allows any origin: any website can call this API from a visitor's browser,"
    + " without their cookies. Set MENAGERIST_CORS_ORIGINS to the origins that need it,"
    + " or leave it empty for same-origin only."
)


class ApiSettings(MenageristBaseSettings):
    """API entrypoint settings."""

    cors_origins: StarOrCSV[Origin] = Field(
        default=[],
        description="Browser origins; empty means same-origin, '*' means any origin.",
    )

    frontend_dist_path: Path | None = Field(
        default=None,
        description="Built frontend directory; unset in API-only mode.",
    )

    trusted_proxies: StarOrCSV[ProxyAddress] = Field(
        default=["127.0.0.1"],
        description="Trusted proxy IPs/CIDRs (CSV); '*' trusts all peers.",
    )


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Return the cached API settings."""
    return ApiSettings()
