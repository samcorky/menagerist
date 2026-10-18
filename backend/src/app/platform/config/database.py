from functools import lru_cache
from typing import Annotated

from pydantic import Field, PostgresDsn

from app.platform.config._base import MenageristBaseSettings


class DatabaseSettings(MenageristBaseSettings):
    """Database connection settings."""

    database_url: Annotated[
        PostgresDsn,
        Field(description="PostgreSQL connection URL for the backend database."),
    ] = PostgresDsn(
        "postgresql+asyncpg://menagerist:menagerist@localhost:5432/menagerist"
    )


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """Return the cached database settings."""
    return DatabaseSettings()
