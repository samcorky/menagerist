from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

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
from app.modules.system.adapters.platform.readiness_check_registry import (
    ReadinessCheckRegistry,
)
from app.modules.system.application.get_health import GetHealth
from app.modules.system.application.get_health_ready import GetHealthReady
from app.modules.system.application.get_version import GetVersion
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_get_health_use_case() -> GetHealth:
    return GetHealth()


def get_get_health_ready_use_case(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> GetHealthReady:
    return GetHealthReady(
        ReadinessCheckRegistry(
            [
                DatabaseConnectivityCheck(session_factory),
                DatabaseMigrationCheck(session_factory),
                DatabasePoolUtilizationCheck(),
            ]
        )
    )


def get_get_version_use_case() -> GetVersion:
    return GetVersion(PackageAppInfoAdapter())
