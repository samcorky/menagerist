import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from cyclopts import App

logger = structlog.get_logger(__name__)

media_app = App(name="media", help="Manage media assets.")


@media_app.command
def cleanup() -> None:
    """Hard-delete staged and orphaned media assets that have passed their TTL."""
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

    settings = get_media_settings()
    now = datetime.now(UTC)

    async def _run() -> int:
        uow = create_media_uow(get_session_factory())
        storage = LocalFilesystemMediaStorage(settings.media_storage_path)
        use_case = CleanupExpiredMedia(uow, storage)
        return await use_case.handle(
            CleanupExpiredMediaCommand(
                staged_before=now - timedelta(hours=settings.staged_ttl_hours),
                orphaned_before=now - timedelta(hours=settings.orphaned_ttl_hours),
            ),
            SYSTEM_ACTOR,
        )

    count = asyncio.run(_run())
    logger.info("media cleanup complete", deleted=count)


@media_app.command
def regenerate_thumbnails(*, max_dimension: int = 320) -> None:
    """Regenerate thumbnails for all attached, thumbnailable media assets.

    Args:
        max_dimension: Longest edge, in pixels, for regenerated thumbnails.
    """
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

    settings = get_media_settings()

    async def _run() -> int:
        uow = create_media_uow(get_session_factory())
        storage = LocalFilesystemMediaStorage(settings.media_storage_path)
        use_case = RegenerateThumbnails(uow, storage, PillowImageProcessor())
        return await use_case.handle(
            RegenerateThumbnailsCommand(max_dimension=max_dimension), SYSTEM_ACTOR
        )

    count = asyncio.run(_run())
    logger.info("thumbnail regeneration complete", regenerated=count)
