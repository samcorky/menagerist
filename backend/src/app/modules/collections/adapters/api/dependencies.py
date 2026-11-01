import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Path

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.collection_definitions import (
    GraphDefinitionChecker,
    get_definition_checker,
)
from app.entrypoints.api.shared.bridges.collection_items import (
    GraphItemLookup,
    get_item_lookup,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
    create_collections_uow,
)
from app.modules.collections.application.add_items_to_collection import (
    AddItemsToCollection,
)
from app.modules.collections.application.count_collection_items import (
    CountCollectionItems,
)
from app.modules.collections.application.create_collection import CreateCollection
from app.modules.collections.application.delete_collection import DeleteCollection
from app.modules.collections.application.get_collection import GetCollection
from app.modules.collections.application.list_collections import ListCollections
from app.modules.collections.application.list_deleted_collections import (
    ListDeletedCollections,
)
from app.modules.collections.application.purge_deleted_collection import (
    PurgeDeletedCollection,
)
from app.modules.collections.application.remove_item_from_collection import (
    RemoveItemFromCollection,
)
from app.modules.collections.application.resolve_collection import (
    ResolveCollection,
    ResolveCollectionQuery,
)
from app.modules.collections.application.restore_collection import RestoreCollection
from app.modules.collections.application.update_collection import UpdateCollection
from app.modules.collections.ports.unit_of_work import (
    CollectionsRepos,
    CollectionsUnitOfWork,
)
from app.platform.database import get_session_factory
from app.shared_kernel.access_guard import AccessGuard
from app.shared_kernel.actor import Actor

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
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    checker: Annotated[GraphDefinitionChecker, Depends(get_definition_checker)],
) -> CreateCollection:
    return CreateCollection(uow, guard, checker)


def get_get_collection_use_case(
    repos: Annotated[CollectionsRepos, Depends(get_collections_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    items: Annotated[GraphItemLookup, Depends(get_item_lookup)],
    checker: Annotated[GraphDefinitionChecker, Depends(get_definition_checker)],
) -> GetCollection:
    return GetCollection(repos, guard, items, checker)


def get_count_collection_items_use_case(
    repos: Annotated[CollectionsRepos, Depends(get_collections_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    items: Annotated[GraphItemLookup, Depends(get_item_lookup)],
) -> CountCollectionItems:
    return CountCollectionItems(repos, guard, items)


def get_list_collections_use_case(
    repos: Annotated[CollectionsRepos, Depends(get_collections_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    items: Annotated[GraphItemLookup, Depends(get_item_lookup)],
) -> ListCollections:
    return ListCollections(repos, guard, items)


def get_update_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    checker: Annotated[GraphDefinitionChecker, Depends(get_definition_checker)],
) -> UpdateCollection:
    return UpdateCollection(uow, guard, checker)


def get_delete_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> DeleteCollection:
    return DeleteCollection(uow, guard)


def get_list_deleted_collections_use_case(
    repos: Annotated[CollectionsRepos, Depends(get_collections_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListDeletedCollections:
    return ListDeletedCollections(repos, guard)


def get_restore_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RestoreCollection:
    return RestoreCollection(uow, guard)


def get_purge_deleted_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> PurgeDeletedCollection:
    return PurgeDeletedCollection(uow, guard)


def get_add_items_to_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    items: Annotated[GraphItemLookup, Depends(get_item_lookup)],
) -> AddItemsToCollection:
    return AddItemsToCollection(uow, guard, items)


def get_remove_item_from_collection_use_case(
    uow: Annotated[CollectionsUnitOfWork, Depends(get_collections_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RemoveItemFromCollection:
    return RemoveItemFromCollection(uow, guard)


def get_resolve_collection_use_case(
    repos: Annotated[CollectionsRepos, Depends(get_collections_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ResolveCollection:
    return ResolveCollection(repos, guard)


async def resolve_collection_id(
    collection_id: Annotated[
        str,
        Path(
            description=(
                "The collection's id (a UUID) or its slug. A slug is looked up "
                + "among your own collections."
            ),
            examples=["01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20", "weekend-watchlist"],
        ),
    ],
    use_case: Annotated[ResolveCollection, Depends(get_resolve_collection_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> uuid.UUID:
    """Turn the `collection_id` path segment, an id or a slug, into the id."""
    return await use_case.handle(
        ResolveCollectionQuery(id_or_slug=collection_id), actor
    )


CollectionIdPath = Annotated[uuid.UUID, Depends(resolve_collection_id)]
