import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.persistence.unit_of_work import build_identity_repos
from app.modules.identity.application.has_administrator import (
    HasAdministrator,
    HasAdministratorQuery,
)
from app.platform.config import INSTANCE_SETTINGS
from app.platform.config.api import CORS_OPEN_HINT, get_api_settings
from app.platform.config.backup import get_backup_settings
from app.platform.config.media import get_media_settings
from app.platform.database import get_session_factory
from app.platform.storage_probe import hint, probe_directory
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
            exists = await HasAdministrator(
                build_identity_repos(session), get_access_guard()
            ).handle(HasAdministratorQuery(), SYSTEM_ACTOR)
    except Exception:
        logger.debug("administrator check skipped", exc_info=True)
        return
    if not exists:
        logger.warning(NO_ADMINISTRATOR_WARNING)


async def warn_if_storage_not_writable() -> None:
    """Log a warning for each configured storage directory that cannot be used."""
    directories = {
        "media": get_media_settings().media_storage_path,
        "backup": get_backup_settings().backup_path,
    }
    for path in directories.values():
        try:
            probe = await asyncio.to_thread(probe_directory, path)
        except Exception:
            logger.debug("storage check skipped", path=str(path), exc_info=True)
            continue
        message = hint(path, probe.state)
        if message is not None:
            logger.warning(message)


async def warn_if_cors_open() -> None:
    """Log one warning when `MENAGERIST_CORS_ORIGINS` allows any origin."""
    if "*" in get_api_settings().cors_origins:
        logger.warning(CORS_OPEN_HINT)


def log_instance_settings() -> None:
    """Log each settings group once at INFO; never prevents start-up."""
    for getter in INSTANCE_SETTINGS:
        try:
            settings = getter()
            logger.info(
                "settings",
                group=type(settings).__name__,
                values=settings.model_dump(mode="json"),
            )
        except Exception:
            logger.debug("settings logging skipped", exc_info=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run start-up checks once per worker, then serve."""
    log_instance_settings()
    await warn_if_storage_not_writable()
    await warn_if_cors_open()
    await warn_if_no_administrator()
    yield
