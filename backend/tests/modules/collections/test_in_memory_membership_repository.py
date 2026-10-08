import uuid
from datetime import UTC, datetime

from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.domain.collection import Membership


def _membership(collection_id: uuid.UUID, item_id: uuid.UUID) -> Membership:
    return Membership(
        collection_id=collection_id, item_id=item_id, added_at=datetime.now(UTC)
    )


async def test_add_and_lookup_both_ways() -> None:
    """Memberships are found from the collection and from the item."""
    repo = InMemoryMembershipRepository()
    shelf_a, shelf_b, item_1, item_2 = (uuid.uuid7() for _ in range(4))
    await repo.add(_membership(shelf_a, item_1))
    await repo.add(_membership(shelf_a, item_2))
    await repo.add(_membership(shelf_b, item_1))

    assert await repo.item_ids(shelf_a) == {item_1, item_2}
    assert await repo.item_ids(shelf_b) == {item_1}
    assert await repo.collection_ids_for(item_1) == {shelf_a, shelf_b}
    assert await repo.collection_ids_for(item_2) == {shelf_a}


async def test_lookups_for_unknown_ids_are_empty() -> None:
    """Unknown collections and items yield empty sets."""
    repo = InMemoryMembershipRepository()
    assert await repo.item_ids(uuid.uuid7()) == set()
    assert await repo.collection_ids_for(uuid.uuid7()) == set()


async def test_adding_twice_stores_one_membership() -> None:
    """A repeated add does not duplicate the pair."""
    repo = InMemoryMembershipRepository()
    shelf, item = uuid.uuid7(), uuid.uuid7()
    await repo.add(_membership(shelf, item))
    await repo.add(_membership(shelf, item))
    assert await repo.item_ids(shelf) == {item}
    await repo.remove(shelf, item)
    assert await repo.item_ids(shelf) == set()


async def test_remove_only_drops_the_given_pair() -> None:
    """Removal leaves other memberships of the item and collection alone."""
    repo = InMemoryMembershipRepository()
    shelf_a, shelf_b, item_1, item_2 = (uuid.uuid7() for _ in range(4))
    for pair in ((shelf_a, item_1), (shelf_a, item_2), (shelf_b, item_1)):
        await repo.add(_membership(*pair))
    await repo.remove(shelf_a, item_1)
    assert await repo.item_ids(shelf_a) == {item_2}
    assert await repo.collection_ids_for(item_1) == {shelf_b}


async def test_removing_a_missing_pair_is_a_no_op() -> None:
    """Removing a pair that was never added raises nothing."""
    repo = InMemoryMembershipRepository()
    await repo.remove(uuid.uuid7(), uuid.uuid7())


async def test_returned_sets_are_copies() -> None:
    """Mutating a returned set does not change what is stored."""
    repo = InMemoryMembershipRepository()
    shelf, item = uuid.uuid7(), uuid.uuid7()
    await repo.add(_membership(shelf, item))
    (await repo.item_ids(shelf)).clear()
    (await repo.collection_ids_for(item)).clear()
    assert await repo.item_ids(shelf) == {item}
    assert await repo.collection_ids_for(item) == {shelf}
