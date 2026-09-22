from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.presets.adapters.persistence.unit_of_work import (
    build_preset_repos,
    create_preset_uow,
)
from app.modules.presets.application.create_preset import CreatePreset
from app.modules.presets.application.delete_preset import DeletePreset
from app.modules.presets.application.get_preset import GetPreset
from app.modules.presets.application.list_presets import ListPresets
from app.modules.presets.application.update_preset import UpdatePreset
from app.modules.presets.ports.unit_of_work import PresetRepos, PresetUnitOfWork
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_preset_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> PresetUnitOfWork:
    """Return a unit of work over the preset table, for commands."""
    return create_preset_uow(session_factory)


async def get_preset_repos(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[PresetRepos]:
    """Return a read-only repository bundle over the preset table, for queries."""
    async with session_factory() as session:
        yield build_preset_repos(session)


def get_create_preset_use_case(
    uow: Annotated[PresetUnitOfWork, Depends(get_preset_uow)],
) -> CreatePreset:
    return CreatePreset(uow)


def get_get_preset_use_case(
    repos: Annotated[PresetRepos, Depends(get_preset_repos)],
) -> GetPreset:
    return GetPreset(repos)


def get_list_presets_use_case(
    repos: Annotated[PresetRepos, Depends(get_preset_repos)],
) -> ListPresets:
    return ListPresets(repos)


def get_update_preset_use_case(
    uow: Annotated[PresetUnitOfWork, Depends(get_preset_uow)],
) -> UpdatePreset:
    return UpdatePreset(uow)


def get_delete_preset_use_case(
    uow: Annotated[PresetUnitOfWork, Depends(get_preset_uow)],
) -> DeletePreset:
    return DeletePreset(uow)
