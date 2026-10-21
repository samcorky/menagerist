"""The guard before the checker, the kind guard order and slug length (review fixes)."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.collections.application.collection_slugs import MAX_SLUG_LENGTH
from app.modules.collections.application.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from app.modules.collections.application.update_collection import (
    UpdateCollection,
    UpdateCollectionCommand,
)
from app.modules.collections.domain.collection import Collection
from app.modules.collections.domain.errors import (
    CollectionKindError,
    InvalidCollectionError,
    InvalidDefinitionError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.collections.domain.definition_warning import DefinitionWarning
    from app.shared_kernel.content_filter import ContentFilter
    from tests.modules.collections.conftest import World

ACTOR = Actor(id=uuid.uuid7())
GOOD: dict[str, Any] = {"v": 1, "where": None}


class _ForbiddenChecker:
    """Fails the test if the checker is reached."""

    async def check(
        self, definition: Mapping[str, Any], scope: ContentFilter
    ) -> list[DefinitionWarning]:
        raise AssertionError("the checker must not be reached")


def _deep() -> dict[str, Any]:
    node: dict[str, Any] = {"v": 1}
    for _ in range(800):
        node = {"d": node}
    return {"v": 1, "deep": node}


HOSTILE: list[dict[str, Any]] = [
    {"v": 1, "note": "a\x00b"},
    {"v": 1, "note": "\ud800"},
    _deep(),
    {"v": 1, "junk": "x" * 1_000_000},
]
HOSTILE_IDS = ["nul", "lone surrogate", "800 deep", "1 MB"]


@pytest.mark.parametrize("definition", HOSTILE, ids=HOSTILE_IDS)
async def test_create_refuses_a_hostile_definition_before_the_checker(
    world: World, definition: dict[str, Any]
) -> None:
    """A definition over the limits is refused and nothing is stored."""
    with pytest.raises(InvalidDefinitionError):
        await CreateCollection(
            world.uow, OwnerAccessPolicy(), _ForbiddenChecker()
        ).handle(CreateCollectionCommand(name="Smart", definition=definition), ACTOR)
    assert world.uow.committed is False


@pytest.mark.parametrize("definition", HOSTILE, ids=HOSTILE_IDS)
async def test_update_refuses_a_hostile_definition_before_the_checker(
    world: World, definition: dict[str, Any]
) -> None:
    """The same guard runs on update, and the stored definition is kept."""
    shelf = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=ACTOR.id, definition=GOOD
    )
    await world.collections.add(shelf)
    with pytest.raises(InvalidDefinitionError):
        await UpdateCollection(
            world.uow, OwnerAccessPolicy(), _ForbiddenChecker()
        ).handle(
            UpdateCollectionCommand(collection_id=shelf.id, definition=definition),
            ACTOR,
        )
    assert shelf.definition == GOOD


async def test_a_manual_collection_given_any_definition_is_a_kind_error(
    world: World,
) -> None:
    """The kind guard runs before the checker, so even junk is the documented 409."""
    shelf = Collection.create(name="M", slug=Slug("m"), owner_id=ACTOR.id)
    await world.collections.add(shelf)
    update = UpdateCollection(world.uow, OwnerAccessPolicy(), _ForbiddenChecker())
    for definition in ({}, {"v": 1, "where": "nope"}, HOSTILE[0]):
        with pytest.raises(CollectionKindError):
            await update.handle(
                UpdateCollectionCommand(collection_id=shelf.id, definition=definition),
                ACTOR,
            )
    assert shelf.definition is None


async def test_a_bad_definition_still_does_not_change_the_name(world: World) -> None:
    """A rejected definition leaves the other fields unchanged."""
    shelf = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=ACTOR.id, definition=GOOD
    )
    await world.collections.add(shelf)
    world.checker.warnings = []
    with pytest.raises(InvalidDefinitionError):
        await UpdateCollection(world.uow, OwnerAccessPolicy(), world.checker).handle(
            UpdateCollectionCommand(
                collection_id=shelf.id,
                name="Renamed",
                definition={"v": 1, "where": "nope"},
            ),
            ACTOR,
        )
    assert shelf.name == "Smart"


async def test_create_with_a_too_long_slug_is_invalid(world: World) -> None:
    """An explicit slug over the limit is a 400; the limit itself is fine."""
    create = CreateCollection(world.uow, OwnerAccessPolicy(), world.checker)
    made = await create.handle(
        CreateCollectionCommand(name="A", slug="a" * MAX_SLUG_LENGTH), ACTOR
    )
    assert len(made.slug.value) == MAX_SLUG_LENGTH
    with pytest.raises(InvalidCollectionError, match="slug"):
        await create.handle(
            CreateCollectionCommand(name="B", slug="a" * (MAX_SLUG_LENGTH + 1)), ACTOR
        )


async def test_update_with_a_too_long_slug_is_invalid(world: World) -> None:
    """The limit applies to a slug change too."""
    shelf = Collection.create(name="M", slug=Slug("m"), owner_id=ACTOR.id)
    await world.collections.add(shelf)
    with pytest.raises(InvalidCollectionError, match="slug"):
        await UpdateCollection(world.uow, OwnerAccessPolicy(), world.checker).handle(
            UpdateCollectionCommand(
                collection_id=shelf.id, slug="b" * (MAX_SLUG_LENGTH + 1)
            ),
            ACTOR,
        )


async def test_a_slug_that_grows_when_normalised_is_still_limited(
    world: World,
) -> None:
    """NFKD can expand a character, so the normalised slug is measured too."""
    with pytest.raises(InvalidCollectionError, match="slug"):
        await CreateCollection(world.uow, OwnerAccessPolicy(), world.checker).handle(
            CreateCollectionCommand(name="B", slug="\u33a2" * 50),
            ACTOR,  # circled 8
        )


async def test_a_derived_slug_from_a_long_expanding_name_fits(world: World) -> None:
    """A name that normalises to more than the limit is truncated, not refused."""
    made = await CreateCollection(world.uow, OwnerAccessPolicy(), world.checker).handle(
        CreateCollectionCommand(name="\u33a2" * 60),
        ACTOR,  # square km, expands to 'km2'
    )
    assert 1 <= len(made.slug.value) <= MAX_SLUG_LENGTH
