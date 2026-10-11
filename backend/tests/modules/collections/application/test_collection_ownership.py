"""Collection use cases with two people: nothing leaks and nothing is written."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.collections.application.add_items_to_collection import (
    AddItemsToCollection,
    AddItemsToCollectionCommand,
)
from app.modules.collections.application.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from app.modules.collections.application.delete_collection import (
    DeleteCollection,
    DeleteCollectionCommand,
)
from app.modules.collections.application.get_collection import (
    GetCollection,
    GetCollectionQuery,
)
from app.modules.collections.application.list_collections import (
    ListCollections,
    ListCollectionsQuery,
)
from app.modules.collections.application.remove_item_from_collection import (
    RemoveItemFromCollection,
    RemoveItemFromCollectionCommand,
)
from app.modules.collections.application.update_collection import (
    UpdateCollection,
    UpdateCollectionCommand,
)
from app.modules.collections.domain.collection import Membership
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ConflictError, ValidationError

if TYPE_CHECKING:
    from tests.modules.collections.conftest import World

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
POLICY = OwnerAccessPolicy()


def _repos(world: World) -> CollectionsRepos:
    return CollectionsRepos(
        collections=world.collections, memberships=world.memberships
    )


async def _create(
    world: World, actor: Actor, name: str = "Jazz", slug: str | None = None
) -> uuid.UUID:
    created = await CreateCollection(world.uow, POLICY).handle(
        CreateCollectionCommand(name=name, slug=slug), actor
    )
    assert created.owner_id == actor.id
    return created.id


async def test_other_user_cannot_get_update_delete_or_remove(world: World) -> None:
    """B gets a not-found for A collection on every route and nothing changes."""
    shelf = await _create(world, ALICE)

    with pytest.raises(CollectionNotFoundError):
        await GetCollection(_repos(world), POLICY, world.items).handle(
            GetCollectionQuery(collection_id=shelf), BOB
        )
    with pytest.raises(CollectionNotFoundError):
        await UpdateCollection(world.uow, POLICY).handle(
            UpdateCollectionCommand(collection_id=shelf, name="Mine now"), BOB
        )
    with pytest.raises(CollectionNotFoundError):
        await RemoveItemFromCollection(world.uow, POLICY).handle(
            RemoveItemFromCollectionCommand(collection_id=shelf, item_id=uuid.uuid7()),
            BOB,
        )
    with pytest.raises(CollectionNotFoundError):
        await DeleteCollection(world.uow, POLICY).handle(
            DeleteCollectionCommand(collection_id=shelf), BOB
        )

    kept = await world.collections.get(shelf, scope=AccessScope.of(ALICE.id))
    assert kept is not None
    assert kept.name == "Jazz"


async def test_list_returns_only_own_collections(world: World) -> None:
    """Each person lists only their own collections."""
    await _create(world, ALICE, "A one")
    await _create(world, ALICE, "A two")
    await _create(world, BOB, "B one")

    handler = ListCollections(_repos(world), POLICY, world.items)
    mine = await handler.handle(ListCollectionsQuery(), ALICE)
    theirs = await handler.handle(ListCollectionsQuery(), BOB)

    assert [s.collection.name for s in mine.items] == ["A one", "A two"]
    assert [s.collection.name for s in theirs.items] == ["B one"]


async def test_list_by_item_ignores_other_users_collections(world: World) -> None:
    """Filtering by item never returns a collection owned by someone else."""
    shelf = await _create(world, ALICE)
    item = uuid.uuid7()
    world.items.live = {item}
    await world.memberships.add(
        Membership(collection_id=shelf, item_id=item, added_at=datetime.now(UTC))
    )

    handler = ListCollections(_repos(world), POLICY, world.items)
    query = ListCollectionsQuery(item_id=item)

    assert len((await handler.handle(query, ALICE)).items) == 1
    assert (await handler.handle(query, BOB)).items == []


async def test_same_name_gives_each_owner_the_plain_slug(world: World) -> None:
    """A and B both get 'jazz'; a second one for A gets '-2'."""
    create = CreateCollection(world.uow, POLICY)
    first = await create.handle(CreateCollectionCommand(name="Jazz"), ALICE)
    other = await create.handle(CreateCollectionCommand(name="Jazz"), BOB)
    again = await create.handle(CreateCollectionCommand(name="Jazz"), ALICE)

    assert (first.slug.value, other.slug.value, again.slug.value) == (
        "jazz",
        "jazz",
        "jazz-2",
    )


async def test_explicit_slug_conflicts_only_within_one_owner(world: World) -> None:
    """The same explicit slug works for B but still conflicts for A."""
    await _create(world, ALICE, slug="mine")

    await _create(world, BOB, "Other", slug="mine")
    with pytest.raises(ConflictError):
        await _create(world, ALICE, "Another", slug="mine")


async def test_cannot_add_to_other_users_collection(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B adding to A collection is not found and writes nothing."""
    shelf = await _create(world, ALICE)
    item = uuid.uuid7()
    world.items.add_owned(item, BOB.id)
    add = AsyncMock(wraps=world.memberships.add)
    monkeypatch.setattr(world.memberships, "add", add)
    world.uow.committed = False

    with pytest.raises(CollectionNotFoundError):
        await AddItemsToCollection(world.uow, POLICY, world.items).handle(
            AddItemsToCollectionCommand(collection_id=shelf, item_ids=[item]), BOB
        )

    add.assert_not_awaited()
    assert world.uow.committed is False


async def test_cannot_add_other_users_item_to_own_collection(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B naming an item of A is rejected like an unknown id; nothing is written."""
    shelf = await _create(world, BOB)
    theirs = uuid.uuid7()
    world.items.add_owned(theirs, ALICE.id)
    add = AsyncMock(wraps=world.memberships.add)
    monkeypatch.setattr(world.memberships, "add", add)
    world.uow.committed = False

    with pytest.raises(ValidationError, match=str(theirs)):
        await AddItemsToCollection(world.uow, POLICY, world.items).handle(
            AddItemsToCollectionCommand(collection_id=shelf, item_ids=[theirs]), BOB
        )

    add.assert_not_awaited()
    assert world.uow.committed is False
    everyone = AccessScope.everyone()
    assert await world.memberships.item_ids(shelf, scope=everyone) == set()


async def test_mixed_own_and_foreign_items_are_rejected_and_nothing_is_written(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One foreign id in the request fails the lot: even own items are not added."""
    shelf = await _create(world, BOB)
    mine, theirs = uuid.uuid7(), uuid.uuid7()
    world.items.add_owned(mine, BOB.id)
    world.items.add_owned(theirs, ALICE.id)
    add = AsyncMock(wraps=world.memberships.add)
    save = AsyncMock(wraps=world.collections.save)
    monkeypatch.setattr(world.memberships, "add", add)
    monkeypatch.setattr(world.collections, "save", save)
    world.uow.committed = False

    with pytest.raises(ValidationError) as excinfo:
        await AddItemsToCollection(world.uow, POLICY, world.items).handle(
            AddItemsToCollectionCommand(collection_id=shelf, item_ids=[mine, theirs]),
            BOB,
        )

    assert str(theirs) in str(excinfo.value)
    assert str(mine) not in str(excinfo.value)
    add.assert_not_awaited()
    save.assert_not_awaited()
    assert world.uow.committed is False
    everyone = AccessScope.everyone()
    assert await world.memberships.item_ids(shelf, scope=everyone) == set()


async def test_item_count_reflects_only_visible_items(world: World) -> None:
    """A member item the viewer cannot see is not counted."""
    shelf = await _create(world, ALICE)
    seen, hidden = uuid.uuid7(), uuid.uuid7()
    world.items.add_owned(seen, ALICE.id)
    world.items.add_owned(hidden, BOB.id)
    for item in (seen, hidden):
        await world.memberships.add(
            Membership(collection_id=shelf, item_id=item, added_at=datetime.now(UTC))
        )

    got = await GetCollection(_repos(world), POLICY, world.items).handle(
        GetCollectionQuery(collection_id=shelf), ALICE
    )
    listed = await ListCollections(_repos(world), POLICY, world.items).handle(
        ListCollectionsQuery(), ALICE
    )

    assert got.item_count == 1
    assert [s.item_count for s in listed.items] == [1]
