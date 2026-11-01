"""How many database connections the server could open, against what Postgres allows."""

from typing import Final

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.platform.config import get_database_settings
from app.platform.config.server import MAX_WORKERS

logger = structlog.get_logger(__name__)

# Each process pools up to POOL_SIZE connections and may open MAX_OVERFLOW more
# under load.
POOL_SIZE: Final = 5
MAX_OVERFLOW: Final = 10
PER_PROCESS: Final = POOL_SIZE + MAX_OVERFLOW
# Postgres keeps this many of `max_connections` back for superusers.
RESERVED: Final = 3
# The background worker is its own process with its own pool.
_BACKGROUND_PROCESSES: Final = 1


def possible_connections(*, workers: int) -> int:
    """The most connections the web workers and the background worker could hold."""
    return (workers + _BACKGROUND_PROCESSES) * PER_PROCESS


def connection_warning(*, workers: int, max_connections: int) -> str | None:
    """Say so when the pools could outgrow Postgres' limit, else return `None`."""
    need = possible_connections(workers=workers)
    if need <= max_connections - RESERVED:
        return None
    return (
        f"Up to {need} database connections could be open ({workers} web "
        + f"worker(s) and the background worker, {PER_PROCESS} each) but Postgres "
        + f"allows {max_connections} ({RESERVED} reserved). Raise "
        + "POSTGRES_MAX_CONNECTIONS or lower MENAGERIST_SERVER_WORKERS."
    )


def validate_workers(workers: int) -> int:
    """Return `workers` if it is a sensible web worker count, else raise."""
    if not 1 <= workers <= MAX_WORKERS:
        msg = (
            "workers must be a whole number between 1 and "
            + f"{MAX_WORKERS}, got {workers}"
        )
        raise ValueError(msg)
    return workers


async def fetch_max_connections() -> int | None:
    """Ask Postgres for `max_connections`, or `None` if it cannot be reached.

    Best effort, on a short-lived engine, so a database that is still starting up
    never stops the server from starting.
    """
    engine = create_async_engine(
        str(get_database_settings().url), connect_args={"timeout": 3}
    )
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SHOW max_connections"))
            return int(result.scalar_one())
    except Exception:
        logger.debug("could not read max_connections", exc_info=True)
        return None
    finally:
        await engine.dispose()
