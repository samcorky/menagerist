import asyncio
import socket
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.platform.config import get_database_settings

if TYPE_CHECKING:
    from collections.abc import Coroutine

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
    settings = get_database_settings()
    return create_async_engine(
        str(settings.url),
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory each unit of work is built from."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


def run_async[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run `coroutine` on a fresh event loop, then release the pooled connections.

    The engine is cached for the process, but `asyncio.run` closes its loop on
    return, and a pooled asyncpg connection cannot outlive the loop that opened it.
    Disposing the engine here lets a long-lived process, such as the interactive
    shell, run several commands in turn. The engine is rebuilt lazily on next use.
    """

    async def run() -> T:
        try:
            return await coroutine
        finally:
            if get_engine.cache_info().currsize:
                await get_engine().dispose()

    return asyncio.run(run())
