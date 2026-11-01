"""Deleted collections: list, restore and purge on in-memory adapters."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.collections.application.list_deleted_collections import (
    ListDeletedCollections,
    ListDeletedCollectionsQuery,
)
from app.modules.collections.application.purge_deleted_collection import (
    PurgeDeletedCollection,
    PurgeDeletedCollectionCommand,
)
from app.modules.collections.application.restore_collection import (
    RestoreCollection,
    RestoreCollectionCommand,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from tests.modules.collections.conftest import World

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
GUARD = InMemoryAccessGuard()


def _lister(world: World) -> ListDeletedCollections:
    repos = CollectionsRepos(
        collections=world.collections, memberships=world.memberships
    )
    return ListDeletedCollections(repos, GUARD)


async def _collection(
    world: World,
    name: str,
    *,
    owner: Actor = ALICE,
    deleted_ago: int | None = None,
    definition: dict[str, Any] | None = None,
) -> Collection:
    collection = Collection.create(
        name=name, slug=Slug(name), owner_id=owner.id, definition=definition
    )
    if deleted_ago is not None:
        collection.soft_delete()
        collection.deleted_at = datetime.now(UTC) - timedelta(minutes=deleted_ago)
    await world.collections.add(collection)
    return collection


async def test_list_shows_only_own_deleted_collections_newest_first(
    world: World,
) -> None:
    """Live collections and other people's deleted content never appear."""
    old = await _collection(world, "Old", deleted_ago=30)
    new = await _collection(world, "New", deleted_ago=5)
    await _collection(world, "Live")
    await _collection(world, "Theirs", owner=BOB, deleted_ago=1)

    result = await _lister(world).handle(ListDeletedCollectionsQuery(), ALICE)

    assert [c.id for c in result.items] == [new.id, old.id]
    assert result.total == 2


async def test_list_pages_by_the_last_row_id(world: World) -> None:
    """`after` continues past the previous page; a stale one gives an empty page."""
    rows = [await _collection(world, str(i), deleted_ago=i) for i in range(1, 5)]
    use_case = _lister(world)

    first = await use_case.handle(ListDeletedCollectionsQuery(limit=3), ALICE)
    second = await use_case.handle(
        ListDeletedCollectionsQuery(after=first.items[-1].id, limit=3), ALICE
    )
    stale = await use_case.handle(
        ListDeletedCollectionsQuery(after=uuid.uuid7()), ALICE
    )

    assert [c.id for c in first.items + second.items] == [r.id for r in rows]
    assert stale.items == []


async def test_restore_a_smart_collection_keeps_its_definition(world: World) -> None:
    """Only the mark is cleared; the saved search is as it was."""
    definition: dict[str, Any] = {"v": 1, "where": None, "sort": []}
    smart = await _collection(world, "Smart", deleted_ago=2, definition=definition)

    result = await RestoreCollection(world.uow, GUARD).handle(
        RestoreCollectionCommand(collection_id=smart.id), ALICE
    )

    assert result.deleted_at is None
    assert result.definition == definition
    assert world.uow.committed
    assert await world.collections.get(smart.id, scope=GUARD.scope_for(ALICE))


async def test_restore_keeps_the_memberships(world: World) -> None:
    """Items on the collection are still on it."""
    shelf = await _collection(world, "Shelf", deleted_ago=2)
    item = uuid.uuid7()
    await world.memberships.add(
        Membership(collection_id=shelf.id, item_id=item, added_at=datetime.now(UTC))
    )

    await RestoreCollection(world.uow, GUARD).handle(
        RestoreCollectionCommand(collection_id=shelf.id), ALICE
    )

    assert await world.memberships.item_ids(shelf.id, scope=GUARD.scope_for(ALICE)) == {
        item
    }


async def test_restore_names_the_slug_clash(world: World) -> None:
    """A live collection with the same slug is a 409 and nothing changes."""
    gone = await _collection(world, "Shelf", deleted_ago=2)
    await world.collections.add(
        Collection.create(name="New shelf", slug=Slug("shelf"), owner_id=ALICE.id)
    )

    with pytest.raises(ConflictError, match="'shelf'"):
        await RestoreCollection(world.uow, GUARD).handle(
            RestoreCollectionCommand(collection_id=gone.id), ALICE
        )

    assert gone.is_deleted
    assert not world.uow.committed


async def test_another_persons_live_slug_is_no_clash(world: World) -> None:
    """Slugs are per owner."""
    mine = await _collection(world, "Shelf", deleted_ago=2)
    await _collection(world, "Shelf", owner=BOB)

    result = await RestoreCollection(world.uow, GUARD).handle(
        RestoreCollectionCommand(collection_id=mine.id), ALICE
    )

    assert not result.is_deleted


@pytest.mark.parametrize("who", ["live", "unknown", "foreign"])
async def test_restore_and_purge_only_find_own_deleted_collections(
    world: World, who: str
) -> None:
    """A live, unknown or another person's collection is not found."""
    live = await _collection(world, "Live")
    foreign = await _collection(world, "Theirs", owner=BOB, deleted_ago=1)
    target = {"live": live.id, "unknown": uuid.uuid7(), "foreign": foreign.id}[who]

    with pytest.raises(CollectionNotFoundError):
        await RestoreCollection(world.uow, GUARD).handle(
            RestoreCollectionCommand(collection_id=target), ALICE
        )
    with pytest.raises(CollectionNotFoundError):
        await PurgeDeletedCollection(world.uow, GUARD).handle(
            PurgeDeletedCollectionCommand(collection_id=target), ALICE
        )

    assert not world.uow.committed
    assert await world.collections.get(live.id, scope=GUARD.scope_for(ALICE))
    assert await world.collections.get_deleted(foreign.id, scope=GUARD.scope_for(BOB))


async def test_purge_removes_the_collection_and_its_memberships_only(
    world: World,
) -> None:
    """Another collection holding the same item keeps it."""
    doomed = await _collection(world, "Doomed", deleted_ago=2)
    other = await _collection(world, "Other")
    item = uuid.uuid7()
    for collection in (doomed, other):
        await world.memberships.add(
            Membership(
                collection_id=collection.id, item_id=item, added_at=datetime.now(UTC)
            )
        )

    await PurgeDeletedCollection(world.uow, GUARD).handle(
        PurgeDeletedCollectionCommand(collection_id=doomed.id), ALICE
    )

    everyone = ContentFilter.everyone()
    assert world.uow.committed
    assert await world.collections.get_deleted(doomed.id, scope=everyone) is None
    assert await world.memberships.collection_ids_for(item, scope=everyone) == {
        other.id
    }
