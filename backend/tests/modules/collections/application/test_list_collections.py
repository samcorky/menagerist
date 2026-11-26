"""Tests for the ListCollections use case."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.modules.collections.application.list_collections import (
    CollectionSort,
    ListCollections,
    ListCollectionsQuery,
)
from app.modules.collections.domain.collection import (
    Collection,
    CollectionKind,
    Membership,
)
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.paging import Cursor, SortOrder

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


def _handler(world: World) -> ListCollections:
    return ListCollections(
        CollectionsRepos(collections=world.collections, memberships=world.memberships),
        InMemoryAccessGuard(),
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
        ListCollectionsQuery(
            limit=2, after=Cursor.after_id(first.items[-1].collection.id)
        ),
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
            item_id=item_id,
            limit=2,
            after=Cursor.after_id(first.items[-1].collection.id),
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
            item_id=item_id,
            limit=2,
            after=Cursor.after_id(first.items[-1].collection.id),
        ),
        SYSTEM_ACTOR,
    )
    third = await _handler(world).handle(
        ListCollectionsQuery(
            item_id=item_id,
            limit=2,
            after=Cursor.after_id(second.items[-1].collection.id),
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


async def test_list_q_filters_by_name(
    world: World, make_collection: MakeCollection
) -> None:
    """`q` keeps only collections whose name or description matches."""
    tapes = make_collection(name="Tapes")
    vinyl = make_collection(name="Vinyl")
    for shelf in (tapes, vinyl):
        await world.collections.add(shelf)

    result = await _handler(world).handle(ListCollectionsQuery(q="tap"), SYSTEM_ACTOR)

    assert [s.collection for s in result.items] == [tapes]


async def test_list_q_with_item_filter_fills_page_across_non_matches(
    world: World, make_collection: MakeCollection
) -> None:
    """`q` and `item_id` combine, and a page stays full across non-matches."""
    names = ["Tape 0", "Vinyl 1", "Vinyl 2", "Tape 3", "Vinyl 4", "Tape 5"]
    shelves = []
    for name in names:
        shelf = make_collection(name=name)
        await world.collections.add(shelf)
        shelves.append(shelf)
    shelves.sort(key=lambda s: s.id)
    item_id = uuid.uuid7()
    for shelf in shelves:
        if shelf.name != "Tape 5":
            await _hold(world, shelf, item_id)

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id, q="tape", limit=2), SYSTEM_ACTOR
    )

    assert [s.collection.name for s in result.items] == ["Tape 0", "Tape 3"]


async def test_list_by_kind_never_summarises_the_other_kind(
    world: World, make_collection: MakeCollection
) -> None:
    """With `kind=manual` a smart row is neither loaded nor counted."""
    from app.shared_kernel.slug import Slug

    manual = make_collection(name="Shelf")
    smart = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=manual.owner_id, definition={"v": 1}
    )
    await world.collections.add(manual)
    await world.collections.add(smart)
    counted: list[object] = []
    original = world.items.count_matching

    async def spy(*args: object, **kwargs: object) -> tuple[int, bool]:
        counted.append(args)
        return await original(*args, **kwargs)  # type: ignore[arg-type]

    world.items.count_matching = spy  # type: ignore[method-assign]

    result = await _handler(world).handle(
        ListCollectionsQuery(kind=CollectionKind.MANUAL), SYSTEM_ACTOR
    )
    assert [s.collection for s in result.items] == [manual]
    assert counted == []

    result = await _handler(world).handle(
        ListCollectionsQuery(kind=CollectionKind.DYNAMIC), SYSTEM_ACTOR
    )
    assert [s.collection for s in result.items] == [smart]
    assert len(counted) == 1


async def test_list_by_kind_still_filters_by_held_item(
    world: World, make_collection: MakeCollection
) -> None:
    """`kind` combines with `item_id`, with the filter applied while paging."""
    shelves = await _add_shelves(world, make_collection, 3)
    item = uuid.uuid7()
    await _hold(world, shelves[2], item)

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item, kind=CollectionKind.MANUAL, limit=1),
        SYSTEM_ACTOR,
    )

    assert [s.collection for s in result.items] == [shelves[2]]


async def _smart(world: World, name: str, definition: dict[str, object]) -> Collection:
    from app.shared_kernel.slug import Slug

    collection = Collection.create(
        name=name,
        slug=Slug(name.lower()),
        owner_id=uuid.uuid7(),
        definition=definition,
    )
    await world.collections.add(collection)
    return collection


async def test_item_id_keeps_held_shelves_and_matching_smart_collections(
    world: World, make_collection: MakeCollection
) -> None:
    """`item_id` keeps shelves holding the item and smart ones whose rule takes it."""
    item = uuid.uuid7()
    world.items.live = {item}
    shelf = make_collection(name="Shelf")
    await world.collections.add(shelf)
    await _hold(world, shelf, item)
    await world.collections.add(make_collection(name="Empty"))
    films = await _smart(world, "Films", {"v": 1, "films": True})
    await _smart(world, "Games", {"v": 1, "games": True})
    world.items.misses.append(({"v": 1, "games": True}, item))

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item), SYSTEM_ACTOR
    )

    assert [s.collection for s in result.items] == [shelf, films]


async def test_item_id_fills_a_page_across_misses(world: World) -> None:
    """A page of matches stays full when misses sit between them."""
    item = uuid.uuid7()
    world.items.live = {item}
    smart = [await _smart(world, f"Smart{n}", {"v": 1, "n": n}) for n in range(5)]
    smart.sort(key=lambda c: c.id)
    for miss in smart[:3]:
        assert miss.definition is not None
        world.items.misses.append((miss.definition, item))

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item, limit=2), SYSTEM_ACTOR
    )

    assert [s.collection for s in result.items] == smart[3:]


@pytest.mark.parametrize("kind", ["manual", "dynamic"])
async def test_item_id_with_a_kind_keeps_that_kind_only(
    world: World, make_collection: MakeCollection, kind: str
) -> None:
    """A kind narrows `item_id` to held shelves or to matching smart collections."""
    item = uuid.uuid7()
    world.items.live = {item}
    shelf = make_collection(name="Shelf")
    await world.collections.add(shelf)
    await _hold(world, shelf, item)
    films = await _smart(world, "Films", {"v": 1})

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item, kind=CollectionKind(kind)), SYSTEM_ACTOR
    )

    expected = shelf if kind == "manual" else films
    assert [s.collection for s in result.items] == [expected]


async def test_item_id_skips_a_smart_collection_with_no_definition(
    world: World,
) -> None:
    """A smart row whose definition is missing has no rule, so it matches nothing."""
    item = uuid.uuid7()
    world.items.live = {item}
    broken = await _smart(world, "Broken", {"v": 1})
    broken.definition = None

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item), SYSTEM_ACTOR
    )

    assert result.items == []


async def test_list_gives_the_next_cursor_only_when_more_follow(
    world: World, make_collection: MakeCollection
) -> None:
    """A full page that ends the list has no `next`; one with more behind it has."""
    shelves = await _add_shelves(world, make_collection, 3)

    first = await _handler(world).handle(ListCollectionsQuery(limit=2), SYSTEM_ACTOR)
    assert first.next is not None
    second = await _handler(world).handle(
        ListCollectionsQuery(limit=2, after=first.next), SYSTEM_ACTOR
    )

    assert [s.collection for s in first.items] == shelves[:2]
    assert [s.collection for s in second.items] == shelves[2:]
    assert second.next is None


async def test_list_sorts_by_a_key_and_a_direction(
    world: World, make_collection: MakeCollection
) -> None:
    """`sort` and `order` reach the repository, and the cursor resumes in that order."""
    for name in ["banana", "Apple", "cherry"]:
        await world.collections.add(make_collection(name=name))

    first = await _handler(world).handle(
        ListCollectionsQuery(limit=2, sort=CollectionSort.NAME, order=SortOrder.DESC),
        SYSTEM_ACTOR,
    )
    assert first.next is not None
    second = await _handler(world).handle(
        ListCollectionsQuery(
            limit=2, sort=CollectionSort.NAME, order=SortOrder.DESC, after=first.next
        ),
        SYSTEM_ACTOR,
    )

    assert [s.collection.name for s in first.items] == ["cherry", "banana"]
    assert [s.collection.name for s in second.items] == ["Apple"]


async def test_list_filter_gives_next_only_when_a_later_collection_holds_the_item(
    world: World, make_collection: MakeCollection
) -> None:
    """The last page that holds the item does not point to an empty page."""
    shelves = await _add_shelves(world, make_collection, 6)
    item_id = uuid.uuid7()
    for shelf in (shelves[0], shelves[2], shelves[5]):
        await _hold(world, shelf, item_id)

    first = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id, limit=2), SYSTEM_ACTOR
    )
    assert first.next is not None
    second = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id, limit=2, after=first.next), SYSTEM_ACTOR
    )

    assert [s.collection for s in first.items] == [shelves[0], shelves[2]]
    assert [s.collection for s in second.items] == [shelves[5]]
    assert second.next is None


async def test_list_filter_has_no_next_when_the_rest_do_not_hold_the_item(
    world: World, make_collection: MakeCollection
) -> None:
    """A full page followed only by other collections is the last page."""
    shelves = await _add_shelves(world, make_collection, 5)
    item_id = uuid.uuid7()
    for shelf in shelves[:2]:
        await _hold(world, shelf, item_id)

    result = await _handler(world).handle(
        ListCollectionsQuery(item_id=item_id, limit=2), SYSTEM_ACTOR
    )

    assert [s.collection for s in result.items] == shelves[:2]
    assert result.next is None
