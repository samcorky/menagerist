import socket
from functools import lru_cache

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.platform.config import get_database_settings

# Errors that mean the database is unreachable rather than the code being wrong.
DATABASE_OUTAGE_ERRORS = (
    InterfaceError,
    OperationalError,
    ConnectionError,
    socket.gaierror,
)


class Base(DeclarativeBase):
    """Shared declarative base every module's persistence models register on."""


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async database engine."""
    return create_async_engine(str(get_database_settings().url))


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory each unit of work is built from."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)
