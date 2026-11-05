from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Any

import structlog
from pydantic import Field, PostgresDsn, SecretStr, field_serializer, model_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.engine import URL

from app.platform.config._base import MenageristBaseSettings
from app.platform.config.dsn import mask_dsn

DRIVER = "postgresql+asyncpg"
PARTS = ("host", "port", "user", "password", "name")

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Generator


class DatabaseSettings(MenageristBaseSettings, group="database"):
    """Database connection settings.

    The connection is either given whole as `url`, or composed from `host`, `port`,
    `user`, `password` and `name`. `url` wins when set; use it for query options such
    as TLS mode, which have no part of their own. `pool_size` and `max_overflow` size
    each process's connection pool. The DSN carries the password, so
    serialisation, `repr` and validation errors show it masked; attribute access still
    returns the real value.
    """

    model_config = SettingsConfigDict(hide_input_in_errors=True)

    url: Annotated[
        PostgresDsn,
        Field(
            description=(
                "PostgreSQL connection URL for the backend database. When set, it "
                + "replaces the host, port, user, password and name settings; use it "
                + "for query options such as TLS mode."
            )
        ),
    ] = PostgresDsn(f"{DRIVER}://menagerist:menagerist@localhost:5432/menagerist")
    host: Annotated[
        str, Field(min_length=1, description="Database server host name or address.")
    ] = "localhost"
    port: Annotated[int, Field(ge=1, le=65535, description="Database server port.")] = (
        5432
    )
    user: Annotated[
        str, Field(min_length=1, description="Database user to connect as.")
    ] = "menagerist"
    password: Annotated[
        SecretStr,
        Field(description="Database password; any characters, no URL encoding."),
    ] = SecretStr("menagerist")
    name: Annotated[
        str, Field(min_length=1, description="Name of the database to use.")
    ] = "menagerist"
    pool_size: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "Database connections each process (every web worker, and the "
                + "background worker) keeps open in its pool."
            ),
        ),
    ] = 5
    max_overflow: Annotated[
        int,
        Field(
            ge=0,
            description=(
                "Extra database connections each process may open beyond the pool "
                + "under load, closed again when idle. 0 caps a process at the pool "
                + "size."
            ),
        ),
    ] = 10

    @property
    def connections_per_process(self) -> int:
        """The most connections one process may hold: its pool plus the overflow."""
        return self.pool_size + self.max_overflow

    @model_validator(mode="after")
    def _compose_url(self) -> DatabaseSettings:
        """Build `url` from the parts unless it was given, escaping the password.

        A given `url` wins; the parts set alongside it are named in a warning, never
        their values.
        """
        if "url" in self.model_fields_set:
            ignored = [name for name in PARTS if name in self.model_fields_set]
            if ignored:
                logger.warning("database_url_overrides_parts", ignored=ignored)
        else:
            composed = URL.create(
                DRIVER,
                username=self.user,
                password=self.password.get_secret_value(),
                host=self.host,
                port=self.port,
                database=self.name,
            ).render_as_string(hide_password=False)
            # Frozen model: set the derived field directly, as validation would.
            object.__setattr__(self, "url", PostgresDsn(composed))
        return self

    @field_serializer("url", when_used="json")
    def _mask_url(self, value: PostgresDsn) -> str:
        return mask_dsn(value)

    def __repr_args__(self) -> Generator[tuple[str | None, Any]]:
        """Mask the DSN password in `repr` and `str`."""
        for name, value in super().__repr_args__():
            yield name, mask_dsn(value) if name == "url" else value


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """Return the cached database settings."""
    return DatabaseSettings()
