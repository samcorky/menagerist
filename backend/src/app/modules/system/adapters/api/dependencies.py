from collections.abc import AsyncIterator
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.scheduler_worker_check import (
    SchedulerWorkerCheck,
)
from app.entrypoints.api.shared.settings_reader import get_settings_reader
from app.modules.system.adapters.persistence.unit_of_work import create_system_uow
from app.modules.system.adapters.persistence.update_check_store import (
    SqlAlchemyUpdateCheckStore,
)
from app.modules.system.adapters.platform.app_info_adapter import PackageAppInfoAdapter
from app.modules.system.adapters.platform.checks.cors_configuration_check import (
    CorsConfigurationCheck,
)
from app.modules.system.adapters.platform.checks.database_connectivity_check import (
    DatabaseConnectivityCheck,
)
from app.modules.system.adapters.platform.checks.database_migration_check import (
    DatabaseMigrationCheck,
)
from app.modules.system.adapters.platform.checks.database_pool_utilization_check import (  # noqa: E501
    DatabasePoolUtilizationCheck,
)
from app.modules.system.adapters.platform.checks.proxy_configuration_check import (
    ProxyConfigurationCheck,
)
from app.modules.system.adapters.platform.checks.storage_check import StorageCheck
from app.modules.system.adapters.platform.readiness_check_registry import (
    ReadinessCheckRegistry,
)
from app.modules.system.adapters.scheduling.jobs import release_provider
from app.modules.system.application.check_for_updates import CheckForUpdates
from app.modules.system.application.get_health import GetHealth
from app.modules.system.application.get_health_ready import GetHealthReady
from app.modules.system.application.get_health_ready_detail import GetHealthReadyDetail
from app.modules.system.application.get_version import GetVersion
from app.modules.system.application.get_version_detail import (
    GetVersionDetail,
    VersionDetailSources,
)
from app.modules.system.application.run_browser_check import RunBrowserCheck
from app.modules.system.application.setting_keys import RELEASE_CHANNEL
from app.modules.system.domain.release import ReleaseChannel
from app.platform.config.api import get_api_settings
from app.platform.config.backup import get_backup_settings
from app.platform.config.media import get_media_settings
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.shared_kernel.access_guard import AccessGuard


def get_get_health_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetHealth:
    return GetHealth(guard)


@lru_cache(maxsize=1)
def get_storage_check() -> StorageCheck:
    """Return the process-wide storage check and its cached probe results."""
    return StorageCheck(
        {
            "media": get_media_settings().storage_path,
            "backup": get_backup_settings().path,
        }
    )


def _readiness_registry(
    session_factory: async_sessionmaker[AsyncSession],
) -> ReadinessCheckRegistry:
    return ReadinessCheckRegistry(
        [
            DatabaseConnectivityCheck(session_factory),
            DatabaseMigrationCheck(session_factory),
            DatabasePoolUtilizationCheck(),
            ProxyConfigurationCheck(),
            CorsConfigurationCheck(get_api_settings().cors_origins),
            get_storage_check(),
            SchedulerWorkerCheck(session_factory),
        ]
    )


def get_get_health_ready_use_case(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetHealthReady:
    return GetHealthReady(_readiness_registry(session_factory), guard)


def get_get_health_ready_detail_use_case(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetHealthReadyDetail:
    return GetHealthReadyDetail(_readiness_registry(session_factory), guard)


def get_get_version_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetVersion:
    return GetVersion(PackageAppInfoAdapter(), guard)


async def get_version_detail_sources(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[VersionDetailSources]:
    """Read the build and the stored release check through a short-lived session."""
    async with session_factory() as session:
        yield VersionDetailSources(
            app_info=PackageAppInfoAdapter(),
            updates=SqlAlchemyUpdateCheckStore(session),
        )


async def get_release_channel() -> ReleaseChannel:
    """The channel the instance follows, from the deployment or an administrator."""
    return ReleaseChannel(await get_settings_reader().get(RELEASE_CHANNEL))


def get_get_version_detail_use_case(
    sources: Annotated[VersionDetailSources, Depends(get_version_detail_sources)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetVersionDetail:
    return GetVersionDetail(sources, guard)


def get_check_for_updates_use_case(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CheckForUpdates:
    return CheckForUpdates(
        create_system_uow(session_factory),
        guard,
        app_info=PackageAppInfoAdapter(),
        provider=release_provider(),
    )


def get_run_browser_check_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RunBrowserCheck:
    return RunBrowserCheck(guard)
