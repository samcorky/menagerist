"""Deployment settings for the web server process."""

from functools import lru_cache
from typing import Annotated, Final, Literal

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings

MAX_WORKERS: Final = 16


class ServerSettings(MenageristBaseSettings, group="server"):
    """How many web worker processes run, and whether this is a container."""

    workers: Annotated[int, Field(ge=1, le=MAX_WORKERS)] | Literal["auto"] = Field(
        default="auto",
        description=(
            f"Web worker processes, 1 to {MAX_WORKERS}, or auto: one per CPU core "
            + "on a host and one in a container or when reloading, as Granian "
            + "advises."
        ),
    )
    in_container: bool | None = Field(
        default=None,
        description=(
            "Whether the server runs in a container. Unset detects it; the image "
            + "sets it, and 0 or 1 overrides detection."
        ),
    )


@lru_cache(maxsize=1)
def get_server_settings() -> ServerSettings:
    """Return the cached server settings."""
    return ServerSettings()
