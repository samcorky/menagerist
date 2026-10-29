"""Scheduled identity housekeeping, composed from the identity use cases."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.identity.adapters.persistence.unit_of_work import create_identity_uow
from app.modules.identity.application.purge_expired_credentials import (
    PurgeExpiredCredentials,
    PurgeExpiredCredentialsCommand,
)
from app.platform.config.identity import get_identity_settings
from app.platform.database import get_session_factory
from app.shared_kernel.jobs import JobContribution, JobDefinition, job

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@job(
    JobDefinition(
        job_key="identity.purge_expired",
        schedule_key="identity.purge_expired_schedule",
        title="Clear expired sign-ins",
        description="Removes sessions and access tokens that have expired.",
    )
)
async def purge_expired_credentials(actor: Actor) -> None:
    """Remove sessions and API tokens that have passed their expiry."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    await PurgeExpiredCredentials(
        create_identity_uow(get_session_factory()), get_access_guard()
    ).handle(PurgeExpiredCredentialsCommand(now=datetime.now(UTC)), actor)


def identity_schedules() -> dict[str, str]:
    """Expose the deployment schedule to the settings-backed schedule source."""
    settings = get_identity_settings()
    return {"identity.purge_expired_schedule": settings.purge_expired_schedule}


def identity_job_contribution() -> JobContribution:
    """The identity module's jobs and their deployment schedule."""
    return JobContribution.from_handlers(
        purge_expired_credentials, schedules=identity_schedules
    )
