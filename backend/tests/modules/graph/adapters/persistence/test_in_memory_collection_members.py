import uuid

from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)


async def test_item_ids_returns_none_for_unknown_collection() -> None:
    """An unregistered collection id gives None."""
    members = InMemoryCollectionMembers()

    assert await members.item_ids(uuid.uuid4()) is None


async def test_item_ids_returns_registered_ids() -> None:
    """A registered collection returns its item ids, including several hundred."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    ids = {uuid.uuid4() for _ in range(500)}
    members.add_collection(collection_id, ids)

    assert await members.item_ids(collection_id) == ids


async def test_item_ids_returns_empty_set_for_empty_collection() -> None:
    """An empty registered collection gives an empty set, not None."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    members.add_collection(collection_id, set())

    assert await members.item_ids(collection_id) == set()


async def test_item_ids_returns_a_copy() -> None:
    """Mutating the returned set does not change the adapter."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    item_id = uuid.uuid4()
    members.add_collection(collection_id, {item_id})

    result = await members.item_ids(collection_id)
    assert result is not None
    result.clear()

    assert await members.item_ids(collection_id) == {item_id}
