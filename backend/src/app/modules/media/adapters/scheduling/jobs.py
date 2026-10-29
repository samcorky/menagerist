"""Scheduled media housekeeping, composed from the media use cases."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.media.adapters.persistence.unit_of_work import create_media_uow
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.application.cleanup_expired_media import (
    CleanupExpiredMedia,
    CleanupExpiredMediaCommand,
)
from app.modules.media.application.remove_stray_media_files import (
    RemoveStrayMediaFiles,
    RemoveStrayMediaFilesCommand,
)
from app.platform.config.media import get_media_settings
from app.platform.database import get_session_factory
from app.shared_kernel.jobs import JobContribution, JobDefinition, job

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
        cleanup_expired_media, remove_stray_media_files, schedules=media_schedules
    )
