import uuid

from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)
from app.shared_kernel.access_scope import AccessScope

_OWNER = uuid.UUID(int=1)
_ALL = AccessScope.everyone()


async def test_item_ids_returns_none_for_unknown_collection() -> None:
    """An unregistered collection id gives None."""
    members = InMemoryCollectionMembers()

    assert await members.item_ids(uuid.uuid4(), _ALL) is None


async def test_item_ids_returns_registered_ids() -> None:
    """A registered collection returns its item ids, including several hundred."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    ids = {uuid.uuid4() for _ in range(500)}
    members.add_collection(collection_id, ids, owner_id=_OWNER)

    assert await members.item_ids(collection_id, AccessScope.of(_OWNER)) == ids
    assert await members.item_ids(collection_id, _ALL) == ids


async def test_item_ids_is_none_outside_the_scope() -> None:
    """Someone else's collection reads as missing, never as empty."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    members.add_collection(collection_id, {uuid.uuid4()}, owner_id=_OWNER)

    other = AccessScope.of(uuid.UUID(int=9))
    assert await members.item_ids(collection_id, other) is None


async def test_item_ids_returns_empty_set_for_empty_collection() -> None:
    """An empty registered collection gives an empty set, not None."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    members.add_collection(collection_id, set(), owner_id=_OWNER)

    assert await members.item_ids(collection_id, _ALL) == set()


async def test_item_ids_returns_a_copy() -> None:
    """Mutating the returned set does not change the adapter."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    item_id = uuid.uuid4()
    members.add_collection(collection_id, {item_id}, owner_id=_OWNER)

    result = await members.item_ids(collection_id, _ALL)
    assert result is not None
    result.clear()

    assert await members.item_ids(collection_id, _ALL) == {item_id}
