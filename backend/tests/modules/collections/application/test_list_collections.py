"""Tests for the ListCollections use case."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.collections.application.list_collections import (
    ListCollections,
    ListCollectionsQuery,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


def _handler(world: World) -> ListCollections:
    return ListCollections(
        CollectionsRepos(collections=world.collections, memberships=world.memberships),
        world.items,
    )


async def _add_shelves(
    world: World, make_collection: MakeCollection, count: int
) -> list[Collection]:
    """Add `count` collections, returned in id order."""
    shelves = [make_collection(name=f"Shelf {n}") for n in range(count)]
    for shelf in shelves:
        await world.collections.add(shelf)
    return sorted(shelves, key=lambda s: s.id)


async def _hold(world: World, shelf: Collection, item_id: uuid.UUID) -> None:
    await world.memberships.add(
        Membership(collection_id=shelf.id, item_id=item_id, added_at=datetime.now(UTC))
    )


async def test_list_orders_by_id_and_excludes_deleted(
    world: World, make_collection: MakeCollection
) -> None:
    """Live collections come back in id order; deleted ones are skipped."""
    shelves = await _add_shelves(world, make_collection, 3)
    shelves[1].soft_delete()

    result = await _handler(world).handle(ListCollectionsQuery(), SYSTEM_ACTOR)

    assert [s.collection for s in result.items] == [shelves[0], shelves[2]]


async def test_list_pages_with_after_and_limit(
    world: World, make_collection: MakeCollection
) -> None:
    """Keyset paging walks the collections without repeats."""
    shelves = await _add_shelves(world, make_collection, 5)

    first = await _handler(world).handle(ListCollectionsQuery(limit=2), SYSTEM_ACTOR)
    second = await _handler(world).handle(
        ListCollectionsQuery(limit=2, after=first.items[-1].collection.id),
        SYSTEM_ACTOR,
    )

    assert [s.collection for s in first.items] == shelves[:2]
    assert [s.collection for s in second.items] == shelves[2:4]


async def test_list_counts_only_live_items(
    world: World, make_collection: MakeCollection
) -> None:
    """item_count ignores members that are no longer live items."""
    shelf, other = await _add_shelves(world, make_collection, 2)
    live, gone = uuid.uuid7(), uuid.uuid7()
    world.items.live = {live}
    await _hold(world, shelf, live)
    await _hold(world, shelf, gone)

    result = await _handler(world).handle(ListCollectionsQuery(), SYSTEM_ACTOR)

    counts = {s.collection.id: s.item_count for s in result.items}
    assert counts == {shelf.id: 1, other.id: 0}
    assert world.uow.committed is False


async def test_list_filters_by_item(
    world: World, make_collection: MakeCollection
) -> None:
    """With item_id only collections holding that item are returned."""
    shelves = await _add_shelves(world, make_collection, 3)
    item_id = uuid.uuid7()
    world.items.live = {item_id}
    await _hold(world, shelves[0], item_id)
    await _hold(world, shelves[2], item_id)

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id), SYSTEM_ACTOR
    )

    assert [s.collection for s in result.items] == [shelves[0], shelves[2]]
    assert [s.item_count for s in result.items] == [1, 1]


async def test_list_filter_fills_page_across_non_matching(
    world: World, make_collection: MakeCollection
) -> None:
    """A filtered page is filled even when non-matching shelves sit between hits."""
    shelves = await _add_shelves(world, make_collection, 6)
    item_id = uuid.uuid7()
    for shelf in (shelves[3], shelves[4], shelves[5]):
        await _hold(world, shelf, item_id)

    first = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id, limit=2), SYSTEM_ACTOR
    )
    second = await _handler(world).handle(
        ListCollectionsQuery(
            item_id=item_id, limit=2, after=first.items[-1].collection.id
        ),
        SYSTEM_ACTOR,
    )

    assert [s.collection for s in first.items] == shelves[3:5]
    assert [s.collection for s in second.items] == [shelves[5]]


async def test_list_filter_with_no_match_is_empty(
    world: World, make_collection: MakeCollection
) -> None:
    """An item on no shelf yields an empty page."""
    await _add_shelves(world, make_collection, 3)

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=uuid.uuid7()), SYSTEM_ACTOR
    )

    assert result.items == []


async def test_list_filter_limit_plus_one_returns_extra_match(
    world: World, make_collection: MakeCollection
) -> None:
    """The router's limit+1 probe gets up to limit+1 filtered matches."""
    shelves = await _add_shelves(world, make_collection, 6)
    item_id = uuid.uuid7()
    for shelf in shelves[1::2]:
        await _hold(world, shelf, item_id)

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id, limit=3), SYSTEM_ACTOR
    )
    probe = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id, limit=4), SYSTEM_ACTOR
    )

    assert [s.collection for s in result.items] == shelves[1::2]
    assert [s.collection for s in probe.items] == shelves[1::2]


async def test_list_filter_matches_exact_multiple_of_batch(
    world: World, make_collection: MakeCollection
) -> None:
    """A total that is an exact multiple of the limit loses nothing across pages."""
    shelves = await _add_shelves(world, make_collection, 4)
    item_id = uuid.uuid7()
    for shelf in shelves:
        await _hold(world, shelf, item_id)

    first = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id, limit=2), SYSTEM_ACTOR
    )
    second = await _handler(world).handle(
        ListCollectionsQuery(
            item_id=item_id, limit=2, after=first.items[-1].collection.id
        ),
        SYSTEM_ACTOR,
    )
    third = await _handler(world).handle(
        ListCollectionsQuery(
            item_id=item_id, limit=2, after=second.items[-1].collection.id
        ),
        SYSTEM_ACTOR,
    )

    assert [s.collection for s in first.items] == shelves[:2]
    assert [s.collection for s in second.items] == shelves[2:]
    assert third.items == []


async def test_list_limit_zero_is_empty(
    world: World, make_collection: MakeCollection
) -> None:
    """A limit of 0 returns nothing, filtered or not."""
    shelves = await _add_shelves(world, make_collection, 2)
    item_id = uuid.uuid7()
    await _hold(world, shelves[0], item_id)

    plain = await _handler(world).handle(ListCollectionsQuery(limit=0), SYSTEM_ACTOR)
    filtered = await _handler(world).handle(
        ListCollectionsQuery(limit=0, item_id=item_id), SYSTEM_ACTOR
    )

    assert plain.items == []
    assert filtered.items == []
