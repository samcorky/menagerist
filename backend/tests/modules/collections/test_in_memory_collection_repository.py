import uuid
from typing import TYPE_CHECKING

from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection


async def test_add_get_and_save_round_trip(make_collection: MakeCollection) -> None:
    """An added collection is retrievable by id and slug; saved changes show."""
    repo = InMemoryCollectionRepository()
    collection = make_collection("Jazz")
    await repo.add(collection)
    assert await repo.get(collection.id) is collection
    assert await repo.get_by_slug("jazz") is collection
    collection.rename("Blues")
    await repo.save(collection)
    stored = await repo.get(collection.id)
    assert stored is not None
    assert stored.name == "Blues"


async def test_unknown_lookups_return_none() -> None:
    """Unknown ids and slugs yield `None`."""
    repo = InMemoryCollectionRepository()
    assert await repo.get(uuid.uuid7()) is None
    assert await repo.get_by_slug("nope") is None


async def test_soft_deleted_collection_is_hidden(
    make_collection: MakeCollection,
) -> None:
    """After a saved soft delete, get, get_by_slug and list skip the collection."""
    repo = InMemoryCollectionRepository()
    collection = make_collection("Jazz")
    await repo.add(collection)
    collection.soft_delete()
    await repo.save(collection)
    assert await repo.get(collection.id) is None
    assert await repo.get_by_slug("jazz") is None
    assert await repo.list(after=None, limit=10) == []


async def test_slug_of_a_deleted_collection_does_not_shadow_a_live_one(
    make_collection: MakeCollection,
) -> None:
    """A live collection reusing a deleted collection's slug is found."""
    repo = InMemoryCollectionRepository()
    old = make_collection("Jazz")
    await repo.add(old)
    old.soft_delete()
    await repo.save(old)
    new = make_collection("Jazz")
    await repo.add(new)
    assert await repo.get_by_slug("jazz") is new


async def test_list_is_ordered_by_id_with_keyset_paging(
    make_collection: MakeCollection,
) -> None:
    """List orders by id and `after` resumes strictly past the given id."""
    repo = InMemoryCollectionRepository()
    made = [make_collection(f"Shelf {n}") for n in range(5)]
    for collection in reversed(made):
        await repo.add(collection)

    first = await repo.list(after=None, limit=2)
    assert first == made[:2]
    second = await repo.list(after=first[-1].id, limit=2)
    assert second == made[2:4]
    last = await repo.list(after=second[-1].id, limit=2)
    assert last == made[4:]
    assert await repo.list(after=last[-1].id, limit=2) == []
