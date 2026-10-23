from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field, PostgresDsn, field_serializer
from pydantic_settings import SettingsConfigDict

from app.platform.config._base import MenageristBaseSettings
from app.platform.config.dsn import mask_dsn

if TYPE_CHECKING:
    from collections.abc import Generator


class DatabaseSettings(MenageristBaseSettings):
    """Database connection settings.

    The DSN carries the password, so serialisation, `repr` and validation errors
    show it masked; attribute access still returns the real value.
    """

    model_config = SettingsConfigDict(hide_input_in_errors=True)

    database_url: Annotated[
        PostgresDsn,
        Field(description="PostgreSQL connection URL for the backend database."),
    ] = PostgresDsn(
        "postgresql+asyncpg://menagerist:menagerist@localhost:5432/menagerist"
    )

    @field_serializer("database_url", when_used="json")
    def _mask_database_url(self, value: PostgresDsn) -> str:
        return mask_dsn(value)

    def __repr_args__(self) -> Generator[tuple[str | None, Any]]:
        """Mask the DSN password in `repr` and `str`."""
        for name, value in super().__repr_args__():
            yield name, mask_dsn(value) if name == "database_url" else value


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """Return the cached database settings."""
    return DatabaseSettings()
