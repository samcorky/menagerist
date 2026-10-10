from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.example_targets import (
    CollectionPackTarget,
    CoverPackTarget,
    GraphPackTarget,
    PresetPackTarget,
    get_collection_pack_target,
    get_cover_pack_target,
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.modules.examples.adapters.persistence.unit_of_work import (
    build_example_repos,
    create_example_uow,
)
from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.application.install_example_pack import InstallExamplePack
from app.modules.examples.application.list_example_entities import ListExampleEntities
from app.modules.examples.application.list_example_packs import ListExamplePacks
from app.modules.examples.application.uninstall_example_pack import UninstallExamplePack
from app.modules.examples.ports.pack_catalogue import PackCatalogue
from app.modules.examples.ports.unit_of_work import ExampleRepos, ExampleUnitOfWork
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_example_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> ExampleUnitOfWork:
    """Return a unit of work over the installations table, for commands."""
    return create_example_uow(session_factory)


async def get_example_repos(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[ExampleRepos]:
    """Return a read-only repository bundle, for queries."""
    async with session_factory() as session:
        yield build_example_repos(session)


@lru_cache(maxsize=1)
def _catalogue() -> FilePackCatalogue:
    return FilePackCatalogue()


def get_pack_catalogue() -> PackCatalogue:
    """Return the shipped-pack catalogue (parsed once per process)."""
    return _catalogue()


def get_list_example_packs_use_case(
    repos: Annotated[ExampleRepos, Depends(get_example_repos)],
    catalogue: Annotated[PackCatalogue, Depends(get_pack_catalogue)],
) -> ListExamplePacks:
    return ListExamplePacks(repos, catalogue)


def get_list_example_entities_use_case(
    repos: Annotated[ExampleRepos, Depends(get_example_repos)],
) -> ListExampleEntities:
    return ListExampleEntities(repos)


def get_install_example_pack_use_case(
    uow: Annotated[ExampleUnitOfWork, Depends(get_example_uow)],
    catalogue: Annotated[PackCatalogue, Depends(get_pack_catalogue)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
    collections: Annotated[CollectionPackTarget, Depends(get_collection_pack_target)],
    covers: Annotated[CoverPackTarget, Depends(get_cover_pack_target)],
) -> InstallExamplePack:
    return InstallExamplePack(uow, catalogue, presets, graph, collections, covers)


def get_uninstall_example_pack_use_case(
    uow: Annotated[ExampleUnitOfWork, Depends(get_example_uow)],
    catalogue: Annotated[PackCatalogue, Depends(get_pack_catalogue)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
    collections: Annotated[CollectionPackTarget, Depends(get_collection_pack_target)],
    covers: Annotated[CoverPackTarget, Depends(get_cover_pack_target)],
) -> UninstallExamplePack:
    return UninstallExamplePack(uow, catalogue, presets, graph, collections, covers)
