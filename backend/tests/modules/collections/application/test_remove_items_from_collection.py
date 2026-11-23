"""Tests for the RemoveItemsFromCollection use case."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.collections.application.add_items_to_collection import (
    AddItemsToCollection,
    AddItemsToCollectionCommand,
)
from app.modules.collections.application.remove_items_from_collection import (
    RemoveItemsFromCollection,
    RemoveItemsFromCollectionCommand,
)
from app.modules.collections.domain.collection import Collection
from app.modules.collections.domain.errors import (
    CollectionKindError,
    CollectionNotFoundError,
)
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


async def _shelve(
    world: World, collection_id: uuid.UUID, count: int
) -> list[uuid.UUID]:
    items = [uuid.uuid7() for _ in range(count)]
    world.items.live.update(items)
    await AddItemsToCollection(world.uow, InMemoryAccessGuard(), world.items).handle(
        AddItemsToCollectionCommand(collection_id=collection_id, item_ids=items),
        SYSTEM_ACTOR,
    )
    return items


def _remove(world: World) -> RemoveItemsFromCollection:
    return RemoveItemsFromCollection(world.uow, InMemoryAccessGuard())


async def test_remove_takes_several_off_and_keeps_the_rest(
    world: World, make_collection: MakeCollection
) -> None:
    """Remove takes several off and keeps the rest."""
    shelf = make_collection()
    await world.collections.add(shelf)
    a, b, c = await _shelve(world, shelf.id, 3)
    world.uow.committed = False

    await _remove(world).handle(
        RemoveItemsFromCollectionCommand(
            collection_id=shelf.id, item_ids=[a, b, uuid.uuid7(), a]
        ),
        SYSTEM_ACTOR,
    )

    assert await world.memberships.item_ids(
        shelf.id, scope=ContentFilter.everyone()
    ) == {c}
    assert world.uow.committed is True


async def test_remove_from_a_smart_collection_is_refused(world: World) -> None:
    """Remove from a smart collection is refused."""
    smart = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=SYSTEM_ACTOR.id, definition={}
    )
    await world.collections.add(smart)

    with pytest.raises(CollectionKindError):
        await _remove(world).handle(
            RemoveItemsFromCollectionCommand(
                collection_id=smart.id, item_ids=[uuid.uuid7()]
            ),
            SYSTEM_ACTOR,
        )


async def test_remove_from_an_unknown_collection_raises_not_found(
    world: World,
) -> None:
    """Remove from an unknown collection raises not found."""
    with pytest.raises(CollectionNotFoundError):
        await _remove(world).handle(
            RemoveItemsFromCollectionCommand(
                collection_id=uuid.uuid7(), item_ids=[uuid.uuid7()]
            ),
            SYSTEM_ACTOR,
        )


async def test_remove_refuses_an_oversized_batch(
    world: World, make_collection: MakeCollection
) -> None:
    """Remove refuses an oversized batch."""
    shelf = make_collection()
    await world.collections.add(shelf)

    with pytest.raises(ValidationError):
        await _remove(world).handle(
            RemoveItemsFromCollectionCommand(
                collection_id=shelf.id, item_ids=[uuid.uuid7() for _ in range(501)]
            ),
            SYSTEM_ACTOR,
        )
