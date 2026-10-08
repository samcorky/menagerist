"""Tests for the CreateCollection use case."""

import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.modules.collections.application.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from app.modules.collections.application.delete_collection import (
    DeleteCollection,
    DeleteCollectionCommand,
)
from app.modules.collections.domain.errors import InvalidCollectionError
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ConflictError

ACTOR = Actor(id=uuid.uuid7())

if TYPE_CHECKING:
    from tests.modules.collections.conftest import World


async def _create(world: World, name: str, slug: str | None = None) -> str:
    """Create a collection and return its slug."""
    created = await CreateCollection(world.uow).handle(
        CreateCollectionCommand(name=name, slug=slug), ACTOR
    )
    return created.slug.value


async def test_slug_is_derived_from_name_and_committed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The slug comes from the name and the collection is stored and committed."""
    add = AsyncMock(wraps=world.collections.add)
    monkeypatch.setattr(world.collections, "add", add)
    created = await CreateCollection(world.uow).handle(
        CreateCollectionCommand(name="  My Vinyl Shelf ", description="d"), ACTOR
    )

    assert created.slug.value == "my-vinyl-shelf"
    assert created.name == "My Vinyl Shelf"
    assert created.description == "d"
    add.assert_awaited_once_with(created)
    assert world.uow.committed is True


async def test_owner_is_the_actor(world: World) -> None:
    """The owner id is taken from the acting user."""
    created = await CreateCollection(world.uow).handle(
        CreateCollectionCommand(name="Shelf"), ACTOR
    )

    assert created.owner_id == ACTOR.id


async def test_derived_slug_gets_numeric_suffixes(world: World) -> None:
    """Repeated names get -2 and -3 suffixes."""
    assert await _create(world, "Shelf") == "shelf"
    assert await _create(world, "Shelf") == "shelf-2"
    assert await _create(world, "Shelf") == "shelf-3"


async def test_symbols_only_name_falls_back_to_collection(world: World) -> None:
    """A name with nothing sluggable uses the literal 'collection'."""
    assert await _create(world, "!!!") == "collection"
    assert await _create(world, "???") == "collection-2"


async def test_explicit_slug_is_normalised(world: World) -> None:
    """An explicit slug is normalised rather than used verbatim."""
    assert await _create(world, "Shelf", "My Slug!") == "my-slug"


async def test_explicit_slug_conflict_raises_conflict(world: World) -> None:
    """An explicit slug held by a live collection is rejected."""
    await _create(world, "Shelf", "taken")
    world.uow.committed = False

    with pytest.raises(ConflictError):
        await _create(world, "Other", "Taken")

    assert world.uow.committed is False


async def test_unslugifiable_explicit_slug_is_invalid(world: World) -> None:
    """A slug with no letters or numbers is a validation error, not a ValueError."""
    with pytest.raises(InvalidCollectionError):
        await _create(world, "Shelf", "!!!")

    assert world.uow.committed is False


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
async def test_invalid_name_raises(world: World, name: str) -> None:
    """Empty, blank or over-long names are rejected without committing."""
    with pytest.raises(InvalidCollectionError):
        await _create(world, name)

    assert world.uow.committed is False


async def test_slug_is_reusable_after_delete(world: World) -> None:
    """A deleted collection's slug can be taken again, explicitly or derived."""
    created = await CreateCollection(world.uow).handle(
        CreateCollectionCommand(name="Shelf"), ACTOR
    )
    await DeleteCollection(world.uow).handle(
        DeleteCollectionCommand(collection_id=created.id), ACTOR
    )

    assert await _create(world, "Shelf") == "shelf"
    assert await _create(world, "Other", "shelf-2") == "shelf-2"


async def test_derived_slug_from_suffixed_name_suffixes_again(world: World) -> None:
    """A name that already slugifies to 'shelf-2' collides to 'shelf-2-2'."""
    assert await _create(world, "Shelf 2") == "shelf-2"
    assert await _create(world, "Shelf 2") == "shelf-2-2"


async def _delete_by_slug(world: World, slug: str) -> None:
    found = await world.collections.get_by_slug(slug)
    assert found is not None
    await DeleteCollection(world.uow).handle(
        DeleteCollectionCommand(collection_id=found.id), ACTOR
    )


async def test_derived_slug_reusable_after_delete(world: World) -> None:
    """Deleting the only 'shelf' frees the derived slug for the next one."""
    assert await _create(world, "Shelf") == "shelf"
    await _delete_by_slug(world, "shelf")

    assert await _create(world, "Shelf") == "shelf"


async def test_derived_slug_fills_gap_left_by_delete(world: World) -> None:
    """With shelf and shelf-2 live, deleting shelf lets the next take 'shelf'."""
    await _create(world, "Shelf")
    await _create(world, "Shelf")
    await _delete_by_slug(world, "shelf")

    assert await _create(world, "Shelf") == "shelf"
    assert await _create(world, "Shelf") == "shelf-3"


@pytest.mark.parametrize(
    ("given", "stored"),
    [("  Notes  ", "Notes"), ("   ", None), ("", None), (None, None)],
)
async def test_create_trims_description_and_blank_becomes_none(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    given: str | None,
    stored: str | None,
) -> None:
    """A blank description is stored as None, like update; others are trimmed."""
    add = AsyncMock(wraps=world.collections.add)
    monkeypatch.setattr(world.collections, "add", add)

    created = await CreateCollection(world.uow).handle(
        CreateCollectionCommand(name="Shelf", description=given), ACTOR
    )

    assert created.description == stored
    add.assert_awaited_once_with(created)
