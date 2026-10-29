"""Scheduled media housekeeping, composed from the media use cases."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.media.adapters.imaging.pillow_processor import PillowImageProcessor
from app.modules.media.adapters.persistence.unit_of_work import create_media_uow
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.application.cleanup_expired_media import (
    CleanupExpiredMedia,
    CleanupExpiredMediaCommand,
)
from app.modules.media.application.regenerate_thumbnails import (
    RegenerateThumbnails,
    RegenerateThumbnailsCommand,
)
from app.modules.media.application.remove_stray_media_files import (
    RemoveStrayMediaFiles,
    RemoveStrayMediaFilesCommand,
)
from app.platform.config.media import get_media_settings
from app.platform.database import get_session_factory
from app.shared_kernel.jobs import JobContribution, JobDefinition, Lane, job

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@job(
    JobDefinition(
        job_key="media.cleanup",
        schedule_key="media.cleanup_schedule",
        title="Clear unused uploads",
        description=(
            "Removes uploads that were never attached and files no longer in use."
        ),
    )
)
async def cleanup_expired_media(actor: Actor) -> None:
    """Delete uploads never attached and files no longer referenced, once expired."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    settings = get_media_settings()
    now = datetime.now(UTC)
    await CleanupExpiredMedia(
        create_media_uow(get_session_factory()),
        get_access_guard(),
        LocalFilesystemMediaStorage(settings.storage_path),
    ).handle(
        CleanupExpiredMediaCommand(
            staged_before=now - timedelta(hours=settings.staged_ttl_hours),
            orphaned_before=now - timedelta(hours=settings.orphaned_ttl_hours),
        ),
        actor,
    )


@job(
    JobDefinition(
        job_key="media.remove_stray_files",
        schedule_key="media.stray_files_schedule",
        title="Clear leftover files",
        description="Removes stored files that no upload refers to any more.",
    )
)
async def remove_stray_media_files(actor: Actor) -> None:
    """Delete stored files with no asset, once old enough not to be an upload."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    settings = get_media_settings()
    await RemoveStrayMediaFiles(
        create_media_uow(get_session_factory()),
        get_access_guard(),
        LocalFilesystemMediaStorage(settings.storage_path),
    ).handle(
        RemoveStrayMediaFilesCommand(
            older_than=datetime.now(UTC) - timedelta(hours=settings.staged_ttl_hours)
        ),
        actor,
    )


@job(
    JobDefinition(
        job_key="media.regenerate_thumbnails",
        lane=Lane.HEAVY,
        title="Rebuild thumbnails",
        description=(
            "Makes every photo's thumbnail again from its original file. "
            + "Useful after an update improves how thumbnails look; "
            + "it can take a while on a large collection."
        ),
        confirm_required=True,
    )
)
async def regenerate_thumbnails(actor: Actor) -> None:
    """Rebuild thumbnails for every attached image, as the media CLI does."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    await RegenerateThumbnails(
        create_media_uow(get_session_factory()),
        get_access_guard(),
        LocalFilesystemMediaStorage(get_media_settings().storage_path),
        PillowImageProcessor(),
    ).handle(RegenerateThumbnailsCommand(), actor)


def media_schedules() -> dict[str, str]:
    """Expose the deployment schedules to the settings-backed schedule source."""
    settings = get_media_settings()
    return {
        "media.cleanup_schedule": settings.cleanup_schedule,
        "media.stray_files_schedule": settings.stray_files_schedule,
    }


def media_job_contribution() -> JobContribution:
    """The media module's jobs and their deployment schedule."""
    return JobContribution.from_handlers(
        cleanup_expired_media,
        remove_stray_media_files,
        regenerate_thumbnails,
        schedules=media_schedules,
    )
