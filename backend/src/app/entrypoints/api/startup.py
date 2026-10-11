from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.adapters.persistence.unit_of_work import build_identity_repos
from app.modules.identity.application.has_administrator import (
    HasAdministrator,
    HasAdministratorQuery,
)
from app.platform.database import get_session_factory
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

logger = structlog.get_logger()

NO_ADMINISTRATOR_WARNING = (
    "No administrator exists yet: open /setup or run `menagerist identity create-admin`"
)


async def warn_if_no_administrator() -> None:
    """Log one warning when no enabled administrator exists.

    A database that cannot be reached yet is not a startup error: the check is
    skipped (readiness already reports the database).
    """
    try:
        async with get_session_factory()() as session:
            exists = await HasAdministrator(build_identity_repos(session)).handle(
                HasAdministratorQuery(), SYSTEM_ACTOR
            )
    except Exception:
        logger.debug("administrator check skipped", exc_info=True)
        return
    if not exists:
        logger.warning(NO_ADMINISTRATOR_WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run start-up checks once per worker, then serve."""
    await warn_if_no_administrator()
    yield
