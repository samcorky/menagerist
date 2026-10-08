"""Tests for the DeleteCollection use case."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.modules.collections.application.delete_collection import (
    DeleteCollection,
    DeleteCollectionCommand,
)
from app.modules.collections.domain.collection import Membership
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


async def test_delete_is_soft_and_keeps_memberships(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The collection is soft-deleted and saved; memberships and items remain."""
    shelf = make_collection()
    await world.collections.add(shelf)
    item_id = uuid.uuid7()
    world.items.live = {item_id}
    await world.memberships.add(
        Membership(collection_id=shelf.id, item_id=item_id, added_at=datetime.now(UTC))
    )

    save = AsyncMock(wraps=world.collections.save)
    monkeypatch.setattr(world.collections, "save", save)

    await DeleteCollection(world.uow).handle(
        DeleteCollectionCommand(collection_id=shelf.id), SYSTEM_ACTOR
    )

    save.assert_awaited_once_with(shelf)
    assert shelf.is_deleted
    assert await world.collections.get(shelf.id) is None
    assert await world.memberships.item_ids(shelf.id) == {item_id}
    assert world.items.live == {item_id}
    assert world.uow.committed is True


async def test_delete_unknown_raises_not_found(world: World) -> None:
    """An unknown id raises CollectionNotFoundError."""
    with pytest.raises(CollectionNotFoundError):
        await DeleteCollection(world.uow).handle(
            DeleteCollectionCommand(collection_id=uuid.uuid7()), SYSTEM_ACTOR
        )

    assert world.uow.committed is False


async def test_delete_already_deleted_raises_not_found(
    world: World, make_collection: MakeCollection
) -> None:
    """Deleting twice reports not found the second time."""
    shelf = make_collection()
    await world.collections.add(shelf)
    command = DeleteCollectionCommand(collection_id=shelf.id)
    await DeleteCollection(world.uow).handle(command, SYSTEM_ACTOR)

    with pytest.raises(CollectionNotFoundError):
        await DeleteCollection(world.uow).handle(command, SYSTEM_ACTOR)
