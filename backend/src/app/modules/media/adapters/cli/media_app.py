import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from cyclopts import App, Parameter

from app.platform.cli_progress import activity, confirm

logger = structlog.get_logger(__name__)

media_app = App(name="media", help="Manage media assets.")


@media_app.command
def cleanup() -> dict[str, object]:
    """Hard-delete staged and orphaned media assets that have passed their TTL."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.modules.media.adapters.persistence.unit_of_work import create_media_uow
    from app.modules.media.adapters.storage.local_filesystem import (
        LocalFilesystemMediaStorage,
    )
    from app.modules.media.application.cleanup_expired_media import (
        CleanupExpiredMedia,
        CleanupExpiredMediaCommand,
    )
    from app.platform.config.media import get_media_settings
    from app.platform.database import get_session_factory
    from app.shared_kernel.actor import SYSTEM_ACTOR

    logger.debug("starting media cleanup")
    settings = get_media_settings()
    now = datetime.now(UTC)

    async def _run() -> int:
        uow = create_media_uow(get_session_factory())
        storage = LocalFilesystemMediaStorage(settings.storage_path)
        use_case = CleanupExpiredMedia(uow, get_access_guard(), storage)
        return await use_case.handle(
            CleanupExpiredMediaCommand(
                staged_before=now - timedelta(hours=settings.staged_ttl_hours),
                orphaned_before=now - timedelta(hours=settings.orphaned_ttl_hours),
            ),
            SYSTEM_ACTOR,
        )

    with activity("Removing expired media"):
        count = asyncio.run(_run())
    logger.info("media cleanup complete", deleted=count)
    return {"message": "Media cleanup complete", "deleted": count}


@media_app.command
def regenerate_thumbnails(
    *,
    max_dimension: int = 320,
    yes: Annotated[bool, Parameter(name=["--yes", "-y"])] = False,
) -> dict[str, object]:
    """Regenerate thumbnails for all attached, thumbnailable media assets.

    Args:
        max_dimension: Longest edge, in pixels, for regenerated thumbnails.
        yes: Do not ask for confirmation.
    """
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.modules.media.adapters.imaging.pillow_processor import PillowImageProcessor
    from app.modules.media.adapters.persistence.unit_of_work import create_media_uow
    from app.modules.media.adapters.storage.local_filesystem import (
        LocalFilesystemMediaStorage,
    )
    from app.modules.media.application.regenerate_thumbnails import (
        RegenerateThumbnails,
        RegenerateThumbnailsCommand,
    )
    from app.platform.config.media import get_media_settings
    from app.platform.database import get_session_factory
    from app.shared_kernel.actor import SYSTEM_ACTOR

    confirm(
        "Rebuild every thumbnail from its original file? This can take a while.",
        assume_yes=yes,
    )
    logger.debug("starting thumbnail regeneration", max_dimension=max_dimension)
    settings = get_media_settings()

    async def _run() -> int:
        uow = create_media_uow(get_session_factory())
        storage = LocalFilesystemMediaStorage(settings.storage_path)
        use_case = RegenerateThumbnails(
            uow, get_access_guard(), storage, PillowImageProcessor()
        )
        return await use_case.handle(
            RegenerateThumbnailsCommand(max_dimension=max_dimension), SYSTEM_ACTOR
        )

    with activity("Regenerating thumbnails"):
        count = asyncio.run(_run())
    logger.info("thumbnail regeneration complete", regenerated=count)
    return {
        "message": "Thumbnails regenerated",
        "regenerated": count,
        "max_dimension": max_dimension,
    }
