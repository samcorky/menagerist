from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from app.platform.config._base import MenageristBaseSettings


class AvatarSettings(MenageristBaseSettings, group="avatars"):
    """Where Random cat gets its cats."""

    cat_service_enabled: bool = Field(
        default=True,
        title="Cat service",
        description=(
            "Whether this instance ever contacts the cat service for Random cat. "
            + "Off makes the button draw a cat in the browser instead. Set by the "
            + "deployment, so an administrator cannot turn it back on from the "
            + "interface."
        ),
    )
    cat_service_url: str = Field(
        default="https://cataas.com",
        title="Cat service address",
        description=(
            "Base address of a cataas-compatible service. The server asks it for "
            + "`/avatar/<random seed>` and stores the reply like an upload; browsers "
            + "never contact it."
        ),
    )

    @field_validator("cat_service_url")
    @classmethod
    def _url_is_a_web_address(cls, value: str) -> str:
        text = value.strip()
        try:
            parts = urlsplit(text)
            usable = parts.scheme in {"http", "https"} and bool(parts.hostname)
            _ = parts.port  # raises for a port that is not a number
        except ValueError:
            usable = False
        if not usable:
            message = "must be an http:// or https:// address with a host"
            raise ValueError(message)
        return text


@lru_cache(maxsize=1)
def get_avatar_settings() -> AvatarSettings:
    """Return the cached avatar settings."""
    return AvatarSettings()
