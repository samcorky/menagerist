"""Wire the settings use cases to the database and the deployment's settings."""

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.settings.adapters.persistence.unit_of_work import (
    build_settings_repos,
    create_settings_uow,
)
from app.modules.settings.adapters.platform.deployment_catalogue import (
    deployment_catalogue,
)
from app.modules.settings.application.get_settings_schema import GetSettingsSchema
from app.modules.settings.application.list_settings import ListSettings
from app.modules.settings.application.reset_setting import ResetSetting
from app.modules.settings.application.settings_reader import CachedSettingsReader
from app.modules.settings.application.update_settings import UpdateSettings
from app.modules.settings.ports.setting_value_repository import SettingValueRepository
from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.shared_kernel.access_guard import AccessGuard


@lru_cache(maxsize=1)
def get_settings_catalogue() -> SettingsCatalogue:
    """The process-wide catalogue: discovered fields and the deployment's pins."""
    return deployment_catalogue()


@lru_cache(maxsize=1)
def get_settings_reader() -> CachedSettingsReader:
    """The process-wide reader other code resolves effective settings through."""
    return CachedSettingsReader(
        get_settings_catalogue(), lambda: create_settings_uow(get_session_factory())
    )


def _invalidate_reader() -> None:
    get_settings_reader().invalidate()


async def get_setting_values(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[SettingValueRepository]:
    """Return a read-only repository over the saved values, for queries."""
    async with session_factory() as session:
        yield build_settings_repos(session).values


def get_list_settings_use_case(
    values: Annotated[SettingValueRepository, Depends(get_setting_values)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    catalogue: Annotated[SettingsCatalogue, Depends(get_settings_catalogue)],
) -> ListSettings:
    return ListSettings(values, guard, catalogue)


def get_get_settings_schema_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    catalogue: Annotated[SettingsCatalogue, Depends(get_settings_catalogue)],
) -> GetSettingsSchema:
    return GetSettingsSchema(catalogue, guard)


def get_update_settings_use_case(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    catalogue: Annotated[SettingsCatalogue, Depends(get_settings_catalogue)],
) -> UpdateSettings:
    return UpdateSettings(
        create_settings_uow(session_factory), guard, catalogue, _invalidate_reader
    )


def get_reset_setting_use_case(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    catalogue: Annotated[SettingsCatalogue, Depends(get_settings_catalogue)],
) -> ResetSetting:
    return ResetSetting(
        create_settings_uow(session_factory), guard, catalogue, _invalidate_reader
    )
