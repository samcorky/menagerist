"""Tests for the RemoveItemFromCollection use case."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.modules.collections.application.add_items_to_collection import (
    AddItemsToCollection,
    AddItemsToCollectionCommand,
)
from app.modules.collections.application.remove_item_from_collection import (
    RemoveItemFromCollection,
    RemoveItemFromCollectionCommand,
)
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


async def _shelve(world: World, collection_id: uuid.UUID, item_id: uuid.UUID) -> int:
    """Put `item_id` on the shelf via the real use case."""
    world.items.live.add(item_id)
    return await AddItemsToCollection(world.uow, world.items).handle(
        AddItemsToCollectionCommand(collection_id=collection_id, item_ids=[item_id]),
        SYSTEM_ACTOR,
    )


async def test_remove_takes_item_off_and_commits(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pair is removed and the change committed; other items stay."""
    shelf = make_collection()
    await world.collections.add(shelf)
    keep, drop = uuid.uuid7(), uuid.uuid7()
    await _shelve(world, shelf.id, keep)
    await _shelve(world, shelf.id, drop)
    remove = AsyncMock(wraps=world.memberships.remove)
    monkeypatch.setattr(world.memberships, "remove", remove)
    world.uow.committed = False

    await RemoveItemFromCollection(world.uow).handle(
        RemoveItemFromCollectionCommand(collection_id=shelf.id, item_id=drop),
        SYSTEM_ACTOR,
    )

    remove.assert_awaited_once_with(shelf.id, drop)
    assert await world.memberships.item_ids(shelf.id) == {keep}
    assert world.uow.committed is True


async def test_remove_absent_item_is_a_no_op_that_commits(
    world: World, make_collection: MakeCollection
) -> None:
    """Removing an item not on the shelf succeeds and changes nothing."""
    shelf = make_collection()
    await world.collections.add(shelf)
    other = uuid.uuid7()
    await _shelve(world, shelf.id, other)

    await RemoveItemFromCollection(world.uow).handle(
        RemoveItemFromCollectionCommand(collection_id=shelf.id, item_id=uuid.uuid7()),
        SYSTEM_ACTOR,
    )

    assert await world.memberships.item_ids(shelf.id) == {other}
    assert world.uow.committed is True


async def test_remove_then_add_again(
    world: World, make_collection: MakeCollection
) -> None:
    """An item taken off the shelf can be added back and counts as new."""
    shelf = make_collection()
    await world.collections.add(shelf)
    item_id = uuid.uuid7()
    await _shelve(world, shelf.id, item_id)
    await RemoveItemFromCollection(world.uow).handle(
        RemoveItemFromCollectionCommand(collection_id=shelf.id, item_id=item_id),
        SYSTEM_ACTOR,
    )

    assert await _shelve(world, shelf.id, item_id) == 1
    assert await world.memberships.item_ids(shelf.id) == {item_id}


async def test_remove_item_deleted_elsewhere(
    world: World, make_collection: MakeCollection
) -> None:
    """An item deleted after being added can still be taken off the shelf."""
    shelf = make_collection()
    await world.collections.add(shelf)
    item_id = uuid.uuid7()
    await _shelve(world, shelf.id, item_id)
    world.items.live.discard(item_id)

    await RemoveItemFromCollection(world.uow).handle(
        RemoveItemFromCollectionCommand(collection_id=shelf.id, item_id=item_id),
        SYSTEM_ACTOR,
    )

    assert await world.memberships.item_ids(shelf.id) == set()


async def test_remove_unknown_collection_raises_not_found(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown collection id raises CollectionNotFoundError."""
    remove = AsyncMock(wraps=world.memberships.remove)
    monkeypatch.setattr(world.memberships, "remove", remove)

    with pytest.raises(CollectionNotFoundError):
        await RemoveItemFromCollection(world.uow).handle(
            RemoveItemFromCollectionCommand(
                collection_id=uuid.uuid7(), item_id=uuid.uuid7()
            ),
            SYSTEM_ACTOR,
        )

    remove.assert_not_awaited()
    assert world.uow.committed is False


async def test_remove_from_deleted_collection_raises_not_found(
    world: World, make_collection: MakeCollection
) -> None:
    """A soft-deleted collection reports not found."""
    shelf = make_collection()
    shelf.soft_delete()
    await world.collections.add(shelf)

    with pytest.raises(CollectionNotFoundError):
        await RemoveItemFromCollection(world.uow).handle(
            RemoveItemFromCollectionCommand(
                collection_id=shelf.id, item_id=uuid.uuid7()
            ),
            SYSTEM_ACTOR,
        )

    assert world.uow.committed is False


async def test_remove_touches_and_saves_collection_once(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing bumps updated_at and saves the collection once, so its ETag moves.

    This also holds when the item was absent: the use case always commits.
    """
    old = datetime(2000, 1, 1, tzinfo=UTC)
    shelf = make_collection()
    await world.collections.add(shelf)
    item_id = uuid.uuid7()
    await _shelve(world, shelf.id, item_id)
    shelf.updated_at = old
    save = AsyncMock(wraps=world.collections.save)
    monkeypatch.setattr(world.collections, "save", save)

    await RemoveItemFromCollection(world.uow).handle(
        RemoveItemFromCollectionCommand(collection_id=shelf.id, item_id=item_id),
        SYSTEM_ACTOR,
    )

    save.assert_awaited_once_with(shelf)
    assert shelf.updated_at > old
    assert world.uow.committed is True


async def test_remove_unknown_collection_does_not_save(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing collection is never saved."""
    save = AsyncMock(wraps=world.collections.save)
    monkeypatch.setattr(world.collections, "save", save)

    with pytest.raises(CollectionNotFoundError):
        await RemoveItemFromCollection(world.uow).handle(
            RemoveItemFromCollectionCommand(
                collection_id=uuid.uuid7(), item_id=uuid.uuid7()
            ),
            SYSTEM_ACTOR,
        )

    save.assert_not_awaited()
    assert world.uow.committed is False
