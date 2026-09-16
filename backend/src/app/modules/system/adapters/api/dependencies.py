from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.system.adapters.platform.app_info_adapter import PackageAppInfoAdapter
from app.modules.system.adapters.platform.health_check_adapter import (
    DatabaseHealthCheckAdapter,
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
    return GetHealthReady(DatabaseHealthCheckAdapter(session_factory))


def get_get_version_use_case() -> GetVersion:
    return GetVersion(PackageAppInfoAdapter())
