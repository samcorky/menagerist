from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.collection_items import GraphItemLookup, get_item_lookup
from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
    create_collections_uow,
)
from app.modules.collections.application.add_items_to_collection import (
    AddItemsToCollection,
)
from app.modules.collections.application.create_collection import CreateCollection
from app.modules.collections.application.delete_collection import DeleteCollection
from app.modules.collections.application.get_collection import GetCollection
from app.modules.collections.application.list_collections import ListCollections
from app.modules.collections.application.remove_item_from_collection import (
    RemoveItemFromCollection,
)
from app.modules.collections.application.update_collection import UpdateCollection
from app.modules.collections.ports.unit_of_work import (
    CollectionsRepos,
    CollectionsUnitOfWork,
)
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_collections_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> CollectionsUnitOfWork:
    """Return a unit of work over the collections tables, for commands."""
    return create_collections_uow(session_factory)


async def get_collections_repos(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[CollectionsRepos]:
    """Return a read-only repository bundle over the collections tables."""
    async with session_factory() as session:
        yield build_collections_repos(session)


def get_create_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
) -> CreateCollection:
    return CreateCollection(uow)


def get_get_collection_use_case(
    repos: Annotated[CollectionsRepos, Depends(get_collections_repos)],
    items: Annotated[GraphItemLookup, Depends(get_item_lookup)],
) -> GetCollection:
    return GetCollection(repos, items)


def get_list_collections_use_case(
    repos: Annotated[CollectionsRepos, Depends(get_collections_repos)],
    items: Annotated[GraphItemLookup, Depends(get_item_lookup)],
) -> ListCollections:
    return ListCollections(repos, items)


def get_update_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
) -> UpdateCollection:
    return UpdateCollection(uow)


def get_delete_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
) -> DeleteCollection:
    return DeleteCollection(uow)


def get_add_items_to_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
    items: Annotated[GraphItemLookup, Depends(get_item_lookup)],
) -> AddItemsToCollection:
    return AddItemsToCollection(uow, items)


def get_remove_item_from_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
) -> RemoveItemFromCollection:
    return RemoveItemFromCollection(uow)
