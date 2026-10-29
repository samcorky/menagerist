"""The jobs the instance can run, composed once for every entrypoint.

The worker, the CLI and the API all read the same catalogue and schedule source, so
what an administrator sees is what the worker runs. A module adds its jobs by
contributing a `JobContribution` to `CONTRIBUTIONS`.
"""

from functools import lru_cache

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.data_jobs import data_job_contribution
from app.entrypoints.api.shared.settings_reader import (
    get_settings_catalogue,
    get_settings_reader,
)
from app.modules.backup.adapters.scheduling.jobs import backup_job_contribution
from app.modules.identity.adapters.scheduling.jobs import identity_job_contribution
from app.modules.media.adapters.scheduling.jobs import media_job_contribution
from app.modules.scheduling.adapters.cli.catalogue import JobCatalogue
from app.modules.scheduling.adapters.cli.jobs import prune_runs_job
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.reader_schedule_source import (
    ReaderScheduleSource,
)
from app.modules.scheduling.application.prune_job_runs import PruneJobRuns
from app.modules.scheduling.application.setting_keys import RUN_HISTORY_PER_JOB
from app.modules.settings.domain.setting import SettingScope
from app.modules.system.adapters.scheduling.jobs import system_job_contribution
from app.platform.database import get_session_factory
from app.shared_kernel.jobs import JobBinding, JobContribution


async def run_history_per_job() -> int:
    """The current quota of completed runs kept per job."""
    return await get_settings_reader().get(RUN_HISTORY_PER_JOB)


def _scheduling_bindings() -> list[JobBinding]:
    return [
        prune_runs_job(
            lambda: PruneJobRuns(
                create_scheduling_uow(get_session_factory()), get_access_guard()
            ),
            keep_per_job=run_history_per_job,
        )
    ]


CONTRIBUTIONS: tuple[JobContribution, ...] = (
    JobContribution(
        bindings=_scheduling_bindings,
        schedules=lambda: {"scheduling.prune_schedule": "0 4 * * *"},
    ),
    backup_job_contribution(),
    identity_job_contribution(),
    media_job_contribution(),
    data_job_contribution(),
    system_job_contribution(),
)


def build_catalogue() -> JobCatalogue:
    """Collect every module's jobs with their handlers."""
    return JobCatalogue(
        binding for item in CONTRIBUTIONS for binding in item.bindings()
    )


def tunable_schedule_keys() -> frozenset[str]:
    """Settings an administrator may change, which a schedule key can name."""
    return frozenset(
        descriptor.key
        for descriptor in get_settings_catalogue().descriptors(SettingScope.INSTANCE)
    )


def build_schedule_source() -> ReaderScheduleSource:
    """Resolve tunable schedules through the settings reader, the rest from env."""
    return ReaderScheduleSource(
        get_settings_reader(),
        live=tunable_schedule_keys(),
        static={
            key: value
            for item in CONTRIBUTIONS
            for key, value in item.schedules().items()
        },
    )


@lru_cache(maxsize=1)
def get_job_catalogue() -> JobCatalogue:
    """The catalogue for this process, built once."""
    return build_catalogue()


def get_schedule_source() -> ReaderScheduleSource:
    """The schedule source for this process."""
    return build_schedule_source()
