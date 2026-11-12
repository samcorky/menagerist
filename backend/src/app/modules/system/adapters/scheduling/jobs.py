"""The scheduled release check, composed from the same use case as Check now."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.system.adapters.persistence.unit_of_work import create_system_uow
from app.modules.system.adapters.platform.app_info_adapter import PackageAppInfoAdapter
from app.modules.system.adapters.platform.ghcr_published_image_provider import (
    GhcrPublishedImageProvider,
)
from app.modules.system.adapters.platform.github_release_provider import (
    GitHubReleaseProvider,
)
from app.modules.system.application.check_for_updates import (
    CheckForUpdates,
    CheckForUpdatesCommand,
)
from app.modules.system.application.setting_keys import RELEASE_CHANNEL
from app.modules.system.domain.release import ReleaseChannel
from app.platform.config.release import get_release_settings
from app.platform.database import get_session_factory
from app.platform.outbound_http import outbound_http
from app.shared_kernel.jobs import JobContribution, JobDefinition, Overlap, job
from app.shared_kernel.progress import NULL_PROGRESS

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.progress import ProgressReporter


def release_provider() -> GitHubReleaseProvider:
    """The release source, reached through the shared outbound client."""
    return GitHubReleaseProvider(outbound_http())


def image_provider() -> GhcrPublishedImageProvider:
    """The registry the edge image is read from, through the same client."""
    return GhcrPublishedImageProvider(outbound_http())


@job(
    JobDefinition(
        job_key="system.update_check",
        schedule_key="release.check_schedule",
        overlap=Overlap.SKIP,
        title="Check for updates",
        description="Looks for a newer Menagerist release on GitHub.",
    )
)
async def check_for_updates(
    actor: Actor, progress: ProgressReporter = NULL_PROGRESS
) -> None:
    """Look for a newer release and keep the answer for the Status page."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.entrypoints.api.shared.settings_reader import get_settings_reader

    await CheckForUpdates(
        create_system_uow(get_session_factory()),
        get_access_guard(),
        app_info=PackageAppInfoAdapter(),
        provider=release_provider(),
        images=image_provider(),
        enabled=get_release_settings().check_enabled,
    ).handle(
        CheckForUpdatesCommand(
            channel=ReleaseChannel(await get_settings_reader().get(RELEASE_CHANNEL)),
            now=datetime.now(UTC),
        ),
        actor,
    )


def system_schedules() -> dict[str, str]:
    """Expose the deployment schedule to the settings-backed schedule source."""
    if not get_release_settings().check_enabled:
        return {}
    return {"release.check_schedule": get_release_settings().check_schedule}


def system_job_contribution() -> JobContribution:
    """The system module's jobs and their deployment schedule.

    With update checks turned off the job is not registered at all, so no cron is
    evaluated and the Scheduled tasks page offers no row to run by hand. Leaving it
    registered with an empty schedule would still show a runnable "Not scheduled"
    row, which is the thing the switch is meant to rule out.
    """
    handlers = (check_for_updates,) if get_release_settings().check_enabled else ()
    return JobContribution.from_handlers(*handlers, schedules=system_schedules)
