from functools import lru_cache
from pathlib import Path  # noqa: TC003 - pydantic resolves the annotation at runtime

from pydantic import Field, field_validator

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._types import Origin, ProxyAddress, StarOrCSV  # noqa: TC001 - pydantic resolves these at runtime

CORS_OPEN_HINT = (
    "CORS allows any origin: any website can call this API from a visitor's browser,"
    + " without their cookies. Set MENAGERIST_API_CORS_ORIGINS to the origins"
    + " that need it,"
    + " or leave it empty for same-origin only."
)


class ApiSettings(MenageristBaseSettings, group="api"):
    """API entrypoint settings."""

    public_origin: Origin | None = Field(
        default=None,
        description=(
            "The address people reach the app at, for example"
            + " https://menagerist.example.com. Other settings default from it;"
            + " each can still be set explicitly."
        ),
    )

    @field_validator("public_origin", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """Treat an empty value (as Compose passes for an unset variable) as unset."""
        return None if value == "" else value

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
