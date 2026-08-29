from functools import lru_cache

from pydantic import PostgresDsn

from app.platform.config._base import MenageristBaseSettings


class DatabaseSettings(MenageristBaseSettings):
    """Database connection settings."""

    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://menagerist:menagerist@localhost:5432/menagerist"
    )


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """Return the cached database settings."""
    return DatabaseSettings()
