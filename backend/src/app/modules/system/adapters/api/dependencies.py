from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.dependencies import get_authorization_port
from app.modules.system.adapters.platform.app_info_adapter import PackageAppInfoAdapter
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
from app.modules.system.application.get_health import GetHealth
from app.modules.system.application.get_health_ready import GetHealthReady
from app.modules.system.application.get_health_ready_detail import GetHealthReadyDetail
from app.modules.system.application.get_version import GetVersion
from app.modules.system.application.get_version_detail import GetVersionDetail
from app.platform.config.backup import get_backup_settings
from app.platform.config.media import get_media_settings
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.shared_kernel.authorization import AuthorizationPort


def get_get_health_use_case() -> GetHealth:
    return GetHealth()


@lru_cache(maxsize=1)
def get_storage_check() -> StorageCheck:
    """Return the process-wide storage check and its cached probe results."""
    return StorageCheck(
        {
            "media": get_media_settings().media_storage_path,
            "backup": get_backup_settings().backup_path,
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
            get_storage_check(),
        ]
    )


def get_get_health_ready_use_case(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> GetHealthReady:
    return GetHealthReady(_readiness_registry(session_factory))


def get_get_health_ready_detail_use_case(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    authorization: Annotated[AuthorizationPort, Depends(get_authorization_port)],
) -> GetHealthReadyDetail:
    return GetHealthReadyDetail(_readiness_registry(session_factory), authorization)


def get_get_version_use_case() -> GetVersion:
    return GetVersion(PackageAppInfoAdapter())


def get_get_version_detail_use_case(
    authorization: Annotated[AuthorizationPort, Depends(get_authorization_port)],
) -> GetVersionDetail:
    return GetVersionDetail(PackageAppInfoAdapter(), authorization)
