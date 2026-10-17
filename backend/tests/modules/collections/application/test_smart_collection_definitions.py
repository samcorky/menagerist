"""Definition validation and counting in the collections use cases."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.collections.application.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from app.modules.collections.application.get_collection import (
    ITEM_COUNT_CAP,
    GetCollection,
    GetCollectionQuery,
)
from app.modules.collections.application.list_collections import (
    ListCollections,
    ListCollectionsQuery,
)
from app.modules.collections.application.update_collection import (
    UpdateCollection,
    UpdateCollectionCommand,
)
from app.modules.collections.domain.collection import Collection
from app.modules.collections.domain.definition_warning import DefinitionWarning
from app.modules.collections.domain.errors import (
    CollectionKindError,
    InvalidCollectionError,
    InvalidDefinitionError,
)
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from tests.modules.collections.conftest import World

ACTOR = Actor(id=uuid.uuid7())
GOOD: dict[str, Any] = {"v": 1, "where": None}
BAD: dict[str, Any] = {"v": 1, "where": "nope"}
STALE = DefinitionWarning(path="where.children[0]", message="gone")


def _get(world: World) -> GetCollection:
    repos = CollectionsRepos(
        collections=world.collections, memberships=world.memberships
    )
    return GetCollection(repos, OwnerAccessPolicy(), world.items, world.checker)


async def _smart(world: World, definition: dict[str, Any] = GOOD) -> Collection:
    shelf = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=ACTOR.id, definition=definition
    )
    await world.collections.add(shelf)
    return shelf


async def test_create_stores_a_valid_definition_exactly_as_sent(world: World) -> None:
    """R21: nothing is rewritten, and an empty `where` is valid."""
    created = await CreateCollection(
        world.uow, OwnerAccessPolicy(), world.checker
    ).handle(CreateCollectionCommand(name="Smart", definition=GOOD), ACTOR)
    assert created.definition == GOOD


async def test_create_rejects_a_malformed_definition_with_its_path(
    world: World,
) -> None:
    """The first bad condition's path is carried by the error and nothing is stored."""
    with pytest.raises(InvalidDefinitionError) as caught:
        await CreateCollection(world.uow, OwnerAccessPolicy(), world.checker).handle(
            CreateCollectionCommand(name="Smart", definition=BAD), ACTOR
        )
    assert caught.value.path == "where"
    assert isinstance(caught.value, InvalidCollectionError)
    assert world.uow.committed is False


async def test_create_without_a_definition_skips_the_check(world: World) -> None:
    """A manual collection is not checked."""
    world.checker.warnings = [STALE]
    created = await CreateCollection(
        world.uow, OwnerAccessPolicy(), world.checker
    ).handle(CreateCollectionCommand(name="Shelf"), ACTOR)
    assert created.definition is None


async def test_update_validates_and_stores_the_definition(world: World) -> None:
    """A valid replacement is stored as sent; a bad one is rejected unchanged."""
    shelf = await _smart(world)
    update = UpdateCollection(world.uow, OwnerAccessPolicy(), world.checker)
    new = {"v": 1, "where": {"op": "and", "children": []}}
    result = await update.handle(
        UpdateCollectionCommand(collection_id=shelf.id, definition=new), ACTOR
    )
    assert result.definition == new
    with pytest.raises(InvalidDefinitionError) as caught:
        await update.handle(
            UpdateCollectionCommand(collection_id=shelf.id, definition=BAD), ACTOR
        )
    assert caught.value.path == "where"
    assert shelf.definition == new


async def test_update_definition_on_a_manual_collection_is_a_kind_error(
    world: World,
) -> None:
    """A manual collection never takes a definition."""
    shelf = Collection.create(name="M", slug=Slug("m"), owner_id=ACTOR.id)
    await world.collections.add(shelf)
    with pytest.raises(CollectionKindError):
        await UpdateCollection(world.uow, OwnerAccessPolicy(), world.checker).handle(
            UpdateCollectionCommand(collection_id=shelf.id, definition=GOOD), ACTOR
        )


async def test_get_returns_the_capped_count_and_warnings(world: World) -> None:
    """A smart collection counts matches, not memberships, and lists warnings."""
    shelf = await _smart(world)
    world.items.live = {uuid.uuid7(), uuid.uuid7()}
    world.checker.warnings = [STALE]
    summary = await _get(world).handle(
        GetCollectionQuery(collection_id=shelf.id), ACTOR
    )
    assert (summary.item_count, summary.item_count_capped) == (2, False)
    assert summary.warnings == (STALE,)


async def test_get_flags_a_count_over_the_cap(world: World) -> None:
    """Above the cap the count stops at it and says so."""
    shelf = await _smart(world)
    world.items.live = {uuid.uuid7() for _ in range(ITEM_COUNT_CAP + 1)}
    summary = await _get(world).handle(
        GetCollectionQuery(collection_id=shelf.id), ACTOR
    )
    assert (summary.item_count, summary.item_count_capped) == (ITEM_COUNT_CAP, True)


async def test_get_degrades_an_invalid_stored_definition_to_a_warning(
    world: World,
) -> None:
    """A definition that no longer validates still loads, with a warning."""
    shelf = await _smart(world, BAD)
    summary = await _get(world).handle(
        GetCollectionQuery(collection_id=shelf.id), ACTOR
    )
    assert [w.path for w in summary.warnings] == ["where"]


async def test_get_of_a_manual_collection_has_no_warnings(world: World) -> None:
    """Manual collections are unchanged."""
    shelf = Collection.create(name="M", slug=Slug("m"), owner_id=ACTOR.id)
    await world.collections.add(shelf)
    world.checker.warnings = [STALE]
    summary = await _get(world).handle(
        GetCollectionQuery(collection_id=shelf.id), ACTOR
    )
    assert (summary.item_count, summary.item_count_capped, summary.warnings) == (
        0,
        False,
        (),
    )


async def test_scope_never_counts_another_owners_items(world: World) -> None:
    """Another owner's items are not counted."""
    shelf = await _smart(world)
    world.items.add_owned(uuid.uuid7(), uuid.uuid7())
    mine = uuid.uuid7()
    world.items.add_owned(mine, ACTOR.id)
    summary = await _get(world).handle(
        GetCollectionQuery(collection_id=shelf.id), ACTOR
    )
    assert summary.item_count == 1


async def test_list_counts_but_does_not_warn(world: World) -> None:
    """The list carries the capped count; warnings stay empty."""
    await _smart(world)
    world.items.live = {uuid.uuid7()}
    world.checker.warnings = [STALE]
    repos = CollectionsRepos(
        collections=world.collections, memberships=world.memberships
    )
    result = await ListCollections(repos, OwnerAccessPolicy(), world.items).handle(
        ListCollectionsQuery(), ACTOR
    )
    assert [(s.item_count, s.warnings) for s in result.items] == [(1, ())]


async def test_in_memory_checker_accepts_an_object_where(world: World) -> None:
    """Only a non-object `where` is malformed."""
    from app.shared_kernel.access_scope import AccessScope

    ok = await world.checker.check({"where": {"op": "and"}}, AccessScope.everyone())
    assert ok == []


async def test_in_memory_lookup_counts_and_caps(world: World) -> None:
    """The in-memory count covers the scope and honours the cap."""
    from app.shared_kernel.access_scope import AccessScope

    world.items.live = {uuid.uuid7() for _ in range(3)}
    scope = AccessScope.everyone()
    assert await world.items.count_matching(GOOD, scope, cap=5) == (3, False)
    assert await world.items.count_matching(GOOD, scope, cap=2) == (2, True)
