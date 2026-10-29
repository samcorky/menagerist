"""The scheduled release check, composed from the same use case as Check now."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.system.adapters.persistence.unit_of_work import create_system_uow
from app.modules.system.adapters.platform.app_info_adapter import PackageAppInfoAdapter
from app.modules.system.adapters.platform.github_release_provider import (
    GitHubReleaseProvider,
)
from app.modules.system.application.check_for_updates import (
    CheckForUpdates,
    CheckForUpdatesCommand,
)
from app.modules.system.application.setting_keys import RELEASE_CHANNEL
from app.modules.system.domain.release import ReleaseChannel
from app.platform.app_info import load_app_info
from app.platform.config.release import get_release_settings
from app.platform.database import get_session_factory
from app.shared_kernel.jobs import JobContribution, JobDefinition, Overlap, job

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


def release_provider() -> GitHubReleaseProvider:
    """The release source, identifying this build to it."""
    return GitHubReleaseProvider(user_agent=f"menagerist/{load_app_info().version}")


@job(
    JobDefinition(
        job_key="system.update_check",
        schedule_key="release.check_schedule",
        overlap=Overlap.SKIP,
        title="Check for updates",
        description="Looks for a newer Menagerist release on GitHub.",
    )
)
async def check_for_updates(actor: Actor) -> None:
    """Look for a newer release and keep the answer for the Status page."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.entrypoints.api.shared.settings_reader import get_settings_reader

    await CheckForUpdates(
        create_system_uow(get_session_factory()),
        get_access_guard(),
        app_info=PackageAppInfoAdapter(),
        provider=release_provider(),
    ).handle(
        CheckForUpdatesCommand(
            channel=ReleaseChannel(await get_settings_reader().get(RELEASE_CHANNEL)),
            now=datetime.now(UTC),
        ),
        actor,
    )


def system_schedules() -> dict[str, str]:
    """Expose the deployment schedule to the settings-backed schedule source."""
    return {"release.check_schedule": get_release_settings().check_schedule}


def system_job_contribution() -> JobContribution:
    """The system module's jobs and their deployment schedule."""
    return JobContribution.from_handlers(check_for_updates, schedules=system_schedules)
