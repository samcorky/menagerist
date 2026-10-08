"""Tests for the GetCollection use case."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.modules.collections.application.get_collection import (
    GetCollection,
    GetCollectionQuery,
)
from app.modules.collections.domain.collection import Membership
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


def _handler(world: World) -> GetCollection:
    return GetCollection(
        CollectionsRepos(collections=world.collections, memberships=world.memberships),
        world.items,
    )


async def test_get_returns_collection_with_live_item_count(
    world: World, make_collection: MakeCollection
) -> None:
    """item_count counts only members that are still live items."""
    shelf = make_collection()
    await world.collections.add(shelf)
    live, gone = uuid.uuid7(), uuid.uuid7()
    world.items.live = {live}
    for item_id in (live, gone):
        await world.memberships.add(
            Membership(
                collection_id=shelf.id, item_id=item_id, added_at=datetime.now(UTC)
            )
        )

    result = await _handler(world).handle(
        GetCollectionQuery(collection_id=shelf.id), SYSTEM_ACTOR
    )

    assert result.collection is shelf
    assert result.item_count == 1
    assert world.uow.committed is False


async def test_get_empty_collection_counts_zero(
    world: World, make_collection: MakeCollection
) -> None:
    """A collection with no members has an item_count of 0."""
    shelf = make_collection()
    await world.collections.add(shelf)

    result = await _handler(world).handle(
        GetCollectionQuery(collection_id=shelf.id), SYSTEM_ACTOR
    )

    assert result.item_count == 0


async def test_get_unknown_raises_not_found(world: World) -> None:
    """An unknown id raises CollectionNotFoundError."""
    with pytest.raises(CollectionNotFoundError):
        await _handler(world).handle(
            GetCollectionQuery(collection_id=uuid.uuid7()), SYSTEM_ACTOR
        )


async def test_get_deleted_raises_not_found(
    world: World, make_collection: MakeCollection
) -> None:
    """A soft-deleted collection is reported as not found."""
    shelf = make_collection()
    shelf.soft_delete()
    await world.collections.add(shelf)

    with pytest.raises(CollectionNotFoundError):
        await _handler(world).handle(
            GetCollectionQuery(collection_id=shelf.id), SYSTEM_ACTOR
        )
