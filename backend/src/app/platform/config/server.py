"""Deployment settings for the web server process."""

from functools import lru_cache
from typing import Annotated, Final, Literal
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Internal

MAX_WORKERS: Final = 16


class ServerSettings(MenageristBaseSettings, group="server"):
    """The server's time zone, its web workers, and whether it is a container."""

    # An empty variable counts as unset: an empty `MENAGERIST_TIME_ZONE` falls through
    # to `TZ` (Docker sets it), and an empty `TZ` to UTC.
    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True)

    time_zone: ZoneInfo = Field(
        default_factory=lambda: ZoneInfo("UTC"),
        validation_alias=AliasChoices("MENAGERIST_TIME_ZONE", "TZ"),
        description=(
            "The server's time zone: when scheduled tasks run, and what 'today' is for "
            + "requests that don't name a zone, such as scripts using an API token. "
            + "Each person's own time zone is set in their preferences."
        ),
    )

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
    kubernetes_service_host: Annotated[
        str | None,
        Field(
            validation_alias="KUBERNETES_SERVICE_HOST",
            description="Set by Kubernetes in every pod; read to detect a container.",
        ),
        Internal(),
    ] = None


@lru_cache(maxsize=1)
def get_server_settings() -> ServerSettings:
    """Return the cached server settings."""
    return ServerSettings()
