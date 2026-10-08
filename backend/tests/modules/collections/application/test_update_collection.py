"""Tests for the UpdateCollection use case."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.modules.collections.application.update_collection import (
    UpdateCollection,
    UpdateCollectionCommand,
)
from app.modules.collections.domain.errors import (
    CollectionNotFoundError,
    InvalidCollectionError,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


async def test_update_changes_name_and_description_not_slug(
    world: World, make_collection: MakeCollection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Name and description change, the slug stays, and the change is saved."""
    shelf = make_collection(name="Old", slug="old")
    shelf.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    await world.collections.add(shelf)
    save = AsyncMock(wraps=world.collections.save)
    monkeypatch.setattr(world.collections, "save", save)

    result = await UpdateCollection(world.uow).handle(
        UpdateCollectionCommand(collection_id=shelf.id, name=" New ", description="d"),
        SYSTEM_ACTOR,
    )

    save.assert_awaited_once_with(result)
    assert result is shelf
    assert (result.name, result.description, result.slug.value) == ("New", "d", "old")
    assert result.updated_at > datetime(2000, 1, 1, tzinfo=UTC)
    assert world.uow.committed is True


async def test_update_description_set_clear_and_unchanged(
    world: World, make_collection: MakeCollection
) -> None:
    """A string sets (trimmed), a blank string clears, None leaves it."""
    shelf = make_collection()
    await world.collections.add(shelf)

    async def update(description: str | None) -> str | None:
        result = await UpdateCollection(world.uow).handle(
            UpdateCollectionCommand(collection_id=shelf.id, description=description),
            SYSTEM_ACTOR,
        )
        return result.description

    assert await update("  about  ") == "about"
    assert await update(None) == "about"
    assert await update("   ") is None
    assert await update("again") == "again"
    assert await update("") is None


async def test_update_leaves_unset_fields_alone(
    world: World, make_collection: MakeCollection
) -> None:
    """Fields left as None are not changed."""
    shelf = make_collection(name="Keep")
    shelf.description = "keep me"
    await world.collections.add(shelf)

    result = await UpdateCollection(world.uow).handle(
        UpdateCollectionCommand(collection_id=shelf.id), SYSTEM_ACTOR
    )

    assert (result.name, result.description) == ("Keep", "keep me")


async def test_update_invalid_name_raises(
    world: World, make_collection: MakeCollection
) -> None:
    """A blank name is rejected without committing."""
    shelf = make_collection()
    await world.collections.add(shelf)

    with pytest.raises(InvalidCollectionError):
        await UpdateCollection(world.uow).handle(
            UpdateCollectionCommand(collection_id=shelf.id, name="  "), SYSTEM_ACTOR
        )

    assert world.uow.committed is False


async def test_update_unknown_raises_not_found(world: World) -> None:
    """An unknown id raises CollectionNotFoundError."""
    with pytest.raises(CollectionNotFoundError):
        await UpdateCollection(world.uow).handle(
            UpdateCollectionCommand(collection_id=uuid.uuid7(), name="x"),
            SYSTEM_ACTOR,
        )

    assert world.uow.committed is False


async def test_update_deleted_raises_not_found(
    world: World, make_collection: MakeCollection
) -> None:
    """A soft-deleted collection cannot be updated."""
    shelf = make_collection()
    shelf.soft_delete()
    await world.collections.add(shelf)

    with pytest.raises(CollectionNotFoundError):
        await UpdateCollection(world.uow).handle(
            UpdateCollectionCommand(collection_id=shelf.id, name="x"), SYSTEM_ACTOR
        )
