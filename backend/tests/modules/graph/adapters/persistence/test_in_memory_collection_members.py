import uuid

from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)
from app.modules.graph.ports.collection_members import ManualSource, SmartSource
from app.shared_kernel.content_filter import ContentFilter

_OWNER = uuid.UUID(int=1)
_ALL = ContentFilter.everyone()
_DEFINITION = {"v": 1, "where": {"op": "and", "children": [{"kind": "text", "q": "a"}]}}


async def test_resolve_returns_none_for_unknown_collection() -> None:
    """An unregistered collection id gives None."""
    members = InMemoryCollectionMembers()

    assert await members.resolve(uuid.uuid4(), _ALL) is None


async def test_resolve_returns_registered_ids() -> None:
    """A manual collection resolves to its item ids, including several hundred."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    ids = {uuid.uuid4() for _ in range(500)}
    members.add_collection(collection_id, ids, owner_id=_OWNER)

    assert await members.resolve(collection_id, ContentFilter.of(_OWNER)) == (
        ManualSource(ids=frozenset(ids))
    )
    assert await members.resolve(collection_id, _ALL) == ManualSource(
        ids=frozenset(ids)
    )


async def test_resolve_is_none_outside_the_scope() -> None:
    """Someone else's collection reads as missing, never as empty."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    members.add_collection(collection_id, {uuid.uuid4()}, owner_id=_OWNER)

    other = ContentFilter.of(uuid.UUID(int=9))
    assert await members.resolve(collection_id, other) is None


async def test_resolve_returns_empty_ids_for_empty_collection() -> None:
    """An empty manual collection gives no ids, not None."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    members.add_collection(collection_id, set(), owner_id=_OWNER)

    assert await members.resolve(collection_id, _ALL) == ManualSource(ids=frozenset())


async def test_resolve_returns_a_smart_collections_definition() -> None:
    """A smart collection resolves to its stored definition."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    members.add_smart_collection(collection_id, _DEFINITION, owner_id=_OWNER)

    assert await members.resolve(collection_id, ContentFilter.of(_OWNER)) == (
        SmartSource(definition=_DEFINITION)
    )


async def test_smart_collection_is_none_outside_the_scope() -> None:
    """Another person's smart collection reads as missing."""
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid4()
    members.add_smart_collection(collection_id, _DEFINITION, owner_id=_OWNER)

    assert await members.resolve(collection_id, ContentFilter.of(uuid.UUID(int=9))) is (
        None
    )
