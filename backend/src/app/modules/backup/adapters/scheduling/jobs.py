"""Scheduled backup jobs, composed from the backup use cases."""

from datetime import timedelta
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.settings_reader import get_settings_reader
from app.modules.backup.application.setting_keys import KEEP_LAST, USER_EXPORT_TTL_HOURS
from app.platform.config.backup import get_backup_settings
from app.platform.config.media import get_media_settings
from app.shared_kernel.jobs import (
    JobBinding,
    JobContribution,
    JobDefinition,
    Lane,
    MissedRun,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.shared_kernel.actor import Actor

type JobStep = Callable[[Actor], Awaitable[object]]


def backup_schedules() -> dict[str, str]:
    """Expose deployment schedules to the settings-backed schedule source."""
    settings = get_backup_settings()
    return {
        "backup.schedule": settings.schedule,
        "backup.prune_exports_schedule": settings.prune_exports_schedule,
    }


async def create_scheduled_backup(actor: Actor) -> object:
    """Back up the shared volumes, refusing to archive a worker that lacks them."""
    from app.entrypoints.api.shared.backup_operations import create_backup

    media_path = get_media_settings().storage_path
    if not media_path.is_dir():
        raise FileNotFoundError(
            f"The media directory {media_path} is missing; "
            + "mount the API's data volumes on the worker."
        )
    return await create_backup(label="scheduled", actor=actor)


async def prune_scheduled_backups(actor: Actor) -> object:
    """Apply the configured retention after a successful scheduled backup."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.modules.backup.adapters.storage.local_backup_store import (
        LocalDirectoryBackupStore,
    )
    from app.modules.backup.application.prune_backups import (
        PruneBackups,
        PruneBackupsCommand,
    )

    settings = get_backup_settings()
    reader = get_settings_reader()
    return await PruneBackups(
        LocalDirectoryBackupStore(settings.path),
        get_access_guard(),
        keep_last=await reader.get(KEEP_LAST),
        pre_migration_keep=settings.pre_migration_keep,
        user_export_ttl_hours=await reader.get(USER_EXPORT_TTL_HOURS),
    ).handle(PruneBackupsCommand(), actor)


async def prune_expired_exports(actor: Actor) -> object:
    """Expire user exports without applying backup retention."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.modules.backup.adapters.storage.local_backup_store import (
        LocalDirectoryBackupStore,
    )
    from app.modules.backup.application.prune_user_exports import (
        PruneUserExports,
        PruneUserExportsCommand,
    )

    settings = get_backup_settings()
    return await PruneUserExports(
        LocalDirectoryBackupStore(settings.path),
        get_access_guard(),
        user_export_ttl_hours=await get_settings_reader().get(USER_EXPORT_TTL_HOURS),
    ).handle(PruneUserExportsCommand(), actor)


def backup_job_bindings(
    *,
    create: JobStep = create_scheduled_backup,
    prune: JobStep = prune_scheduled_backups,
    prune_exports: JobStep = prune_expired_exports,
) -> list[JobBinding]:
    """Bind backups with retention after each success, and hourly export expiry."""

    async def create_then_prune(actor: Actor) -> None:
        await create(actor)
        await prune(actor)

    async def expire_exports(actor: Actor) -> None:
        await prune_exports(actor)

    return [
        JobBinding(
            definition=JobDefinition(
                job_key="backup.create",
                lane=Lane.HEAVY,
                missed_run=MissedRun.RUN_ONCE,
                max_lateness=timedelta(hours=12),
                schedule_key="backup.schedule",
                title="Back up everything",
                description="Saves a full copy of your collection, keeping the newest.",
            ),
            handler=create_then_prune,
        ),
        JobBinding(
            definition=JobDefinition(
                job_key="backup.prune_exports",
                schedule_key="backup.prune_exports_schedule",
                title="Clear expired exports",
                description="Removes personal exports once they have expired.",
            ),
            handler=expire_exports,
        ),
    ]


def backup_job_contribution() -> JobContribution:
    """The backup module's jobs and their deployment schedules."""
    return JobContribution(bindings=backup_job_bindings, schedules=backup_schedules)
