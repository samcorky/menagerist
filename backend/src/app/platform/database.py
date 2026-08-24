from functools import lru_cache

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base every module's persistence models register on."""


class DatabaseSettings(BaseSettings):
    """Database connection configuration, read from the environment.

    Defaults match `compose.yaml`'s `postgres` service, so local
    development works with no `.env` beyond `docker compose up -d`. Uses the
    `asyncpg` driver rather than psycopg's async mode - asyncpg has no
    dependency on `loop.add_reader`/`add_writer`, so it runs under any
    event loop implementation (including Windows' default `ProactorEventLoop`,
    which psycopg's async mode cannot use) with no platform-specific setup.
    """

    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://menagerist:menagerist@localhost:5432/menagerist"
    )


@lru_cache(maxsize=1)
def load_database_settings() -> DatabaseSettings:
    """Load database settings from the environment."""
    return DatabaseSettings()


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async database engine."""
    return create_async_engine(str(load_database_settings().database_url))


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory each unit of work is built from."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)
