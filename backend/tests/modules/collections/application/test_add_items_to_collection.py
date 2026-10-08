"""Tests for the AddItemsToCollection use case."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.modules.collections.application.add_items_to_collection import (
    MAX_ITEMS_PER_REQUEST,
    AddItemsToCollection,
    AddItemsToCollectionCommand,
)
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


def _handler(world: World) -> AddItemsToCollection:
    """Build the use case over `world`."""
    return AddItemsToCollection(world.uow, world.items)


async def test_add_several_returns_count(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every live item is added and the count is returned after one commit."""
    shelf = make_collection()
    await world.collections.add(shelf)
    ids = [uuid.uuid7() for _ in range(3)]
    world.items.live = set(ids)
    add = AsyncMock(wraps=world.memberships.add)
    monkeypatch.setattr(world.memberships, "add", add)

    count = await _handler(world).handle(
        AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=ids), SYSTEM_ACTOR
    )

    assert count == 3
    assert add.await_count == 3
    assert await world.memberships.item_ids(shelf.id) == set(ids)
    assert world.uow.committed is True


async def test_add_skips_duplicates_and_present_items(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeated ids and items already on the shelf are not counted or re-added."""
    shelf = make_collection()
    await world.collections.add(shelf)
    first, second = uuid.uuid7(), uuid.uuid7()
    world.items.live = {first, second}
    command = AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=[first])
    await _handler(world).handle(command, SYSTEM_ACTOR)
    add = AsyncMock(wraps=world.memberships.add)
    monkeypatch.setattr(world.memberships, "add", add)

    count = await _handler(world).handle(
        AddItemsToCollectionCommand(
            collection_id=shelf.id, item_ids=[second, first, second]
        ),
        SYSTEM_ACTOR,
    )

    assert count == 1
    assert add.await_count == 1
    assert add.await_args is not None
    assert add.await_args.args[0].item_id == second
    assert await world.memberships.item_ids(shelf.id) == {first, second}


async def test_add_non_live_ids_raise_naming_them_and_add_nothing(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown or deleted ids are named, sorted, and nothing at all is added."""
    shelf = make_collection()
    await world.collections.add(shelf)
    good = uuid.uuid7()
    bad_a, bad_b = uuid.uuid7(), uuid.uuid7()
    world.items.live = {good}
    add = AsyncMock(wraps=world.memberships.add)
    monkeypatch.setattr(world.memberships, "add", add)

    with pytest.raises(ValidationError) as excinfo:
        await _handler(world).handle(
            AddItemsToCollectionCommand(
                collection_id=shelf.id, item_ids=[bad_b, good, bad_a]
            ),
            SYSTEM_ACTOR,
        )

    first, second = sorted([str(bad_a), str(bad_b)])
    assert str(excinfo.value) == f"Unknown or deleted items: {first}, {second}"
    assert str(good) not in str(excinfo.value)
    add.assert_not_awaited()
    assert await world.memberships.item_ids(shelf.id) == set()
    assert world.uow.committed is False


async def test_add_deleted_item_is_rejected(
    world: World, make_collection: MakeCollection
) -> None:
    """An item that is no longer live is rejected like an unknown id."""
    shelf = make_collection()
    await world.collections.add(shelf)
    item_id = uuid.uuid7()
    world.items.live = {item_id}
    world.items.live.discard(item_id)

    with pytest.raises(ValidationError, match=str(item_id)):
        await _handler(world).handle(
            AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=[item_id]),
            SYSTEM_ACTOR,
        )

    assert world.uow.committed is False


async def test_add_unknown_collection_raises_not_found(world: World) -> None:
    """An unknown collection id raises CollectionNotFoundError."""
    with pytest.raises(CollectionNotFoundError):
        await _handler(world).handle(
            AddItemsToCollectionCommand(collection_id=uuid.uuid7(), item_ids=[]),
            SYSTEM_ACTOR,
        )

    assert world.uow.committed is False


async def test_add_to_deleted_collection_raises_not_found(
    world: World, make_collection: MakeCollection
) -> None:
    """A soft-deleted collection reports not found."""
    shelf = make_collection()
    shelf.soft_delete()
    await world.collections.add(shelf)
    item_id = uuid.uuid7()
    world.items.live = {item_id}

    with pytest.raises(CollectionNotFoundError):
        await _handler(world).handle(
            AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=[item_id]),
            SYSTEM_ACTOR,
        )

    assert await world.memberships.item_ids(shelf.id) == set()
    assert world.uow.committed is False


async def test_add_empty_request_is_a_no_op(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty request returns 0 without writing or committing."""
    shelf = make_collection()
    await world.collections.add(shelf)
    add = AsyncMock(wraps=world.memberships.add)
    monkeypatch.setattr(world.memberships, "add", add)

    count = await _handler(world).handle(
        AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=[]), SYSTEM_ACTOR
    )

    assert count == 0
    add.assert_not_awaited()
    assert world.uow.committed is False


async def test_add_over_limit_is_rejected(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """More than the per-request cap raises ValidationError before any work."""
    shelf = make_collection()
    await world.collections.add(shelf)
    ids = [uuid.uuid7() for _ in range(MAX_ITEMS_PER_REQUEST + 1)]
    world.items.live = set(ids)
    add = AsyncMock(wraps=world.memberships.add)
    monkeypatch.setattr(world.memberships, "add", add)

    with pytest.raises(ValidationError, match=str(MAX_ITEMS_PER_REQUEST)):
        await _handler(world).handle(
            AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=ids),
            SYSTEM_ACTOR,
        )

    add.assert_not_awaited()
    assert world.uow.committed is False


async def test_add_exactly_the_limit_is_accepted(
    world: World, make_collection: MakeCollection
) -> None:
    """A request of exactly the cap succeeds."""
    shelf = make_collection()
    await world.collections.add(shelf)
    ids = [uuid.uuid7() for _ in range(MAX_ITEMS_PER_REQUEST)]
    world.items.live = set(ids)

    count = await _handler(world).handle(
        AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=ids), SYSTEM_ACTOR
    )

    assert count == MAX_ITEMS_PER_REQUEST


_OLD = datetime(2000, 1, 1, tzinfo=UTC)


async def test_add_touches_and_saves_collection_once(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real add bumps updated_at and saves the collection once, so its ETag moves."""
    shelf = make_collection()
    shelf.updated_at = _OLD
    await world.collections.add(shelf)
    item_id = uuid.uuid7()
    world.items.live = {item_id}
    save = AsyncMock(wraps=world.collections.save)
    monkeypatch.setattr(world.collections, "save", save)

    await _handler(world).handle(
        AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=[item_id]),
        SYSTEM_ACTOR,
    )

    save.assert_awaited_once_with(shelf)
    assert shelf.updated_at > _OLD
    assert world.uow.committed is True


async def test_add_of_present_items_does_not_touch_or_commit(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding only items already on the shelf leaves the collection untouched."""
    shelf = make_collection()
    await world.collections.add(shelf)
    item_id = uuid.uuid7()
    world.items.live = {item_id}
    command = AddItemsToCollectionCommand(collection_id=shelf.id, item_ids=[item_id])
    await _handler(world).handle(command, SYSTEM_ACTOR)
    shelf.updated_at = _OLD
    world.uow.committed = False
    save = AsyncMock(wraps=world.collections.save)
    monkeypatch.setattr(world.collections, "save", save)

    count = await _handler(world).handle(command, SYSTEM_ACTOR)

    assert count == 0
    save.assert_not_awaited()
    assert shelf.updated_at == _OLD
    assert world.uow.committed is False


async def test_add_failure_does_not_save_collection(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected request neither saves the collection nor commits."""
    shelf = make_collection()
    shelf.updated_at = _OLD
    await world.collections.add(shelf)
    save = AsyncMock(wraps=world.collections.save)
    monkeypatch.setattr(world.collections, "save", save)

    with pytest.raises(ValidationError):
        await _handler(world).handle(
            AddItemsToCollectionCommand(
                collection_id=shelf.id, item_ids=[uuid.uuid7()]
            ),
            SYSTEM_ACTOR,
        )

    save.assert_not_awaited()
    assert shelf.updated_at == _OLD
    assert world.uow.committed is False
