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


async def test_list_q_matches_name_or_description_ignoring_case(
    make_collection: MakeCollection,
) -> None:
    """`q` keeps collections whose name or description contains it."""
    repo = InMemoryCollectionRepository()
    by_name = make_collection("Tapes")
    by_description = make_collection("Other")
    by_description.description = "Old TAPE reels"
    miss = make_collection("Vinyl")
    for collection in (by_name, by_description, miss):
        await repo.add(collection)

    found = await repo.list(after=None, limit=10, q="tape")

    assert {c.id for c in found} == {by_name.id, by_description.id}


async def test_list_q_treats_percent_and_underscore_literally(
    make_collection: MakeCollection,
) -> None:
    """Wildcard characters in `q` match only themselves."""
    repo = InMemoryCollectionRepository()
    percent = make_collection("50% off")
    plain = make_collection("500 things")
    underscore = make_collection("a_b")
    other = make_collection("axb")
    for collection in (percent, plain, underscore, other):
        await repo.add(collection)

    assert await repo.list(after=None, limit=10, q="50%") == [percent]
    assert await repo.list(after=None, limit=10, q="a_b") == [underscore]


async def test_list_blank_q_returns_everything(
    make_collection: MakeCollection,
) -> None:
    """`None`, empty and whitespace-only `q` apply no filter."""
    repo = InMemoryCollectionRepository()
    for name in ("A", "B"):
        await repo.add(make_collection(name))

    for q in (None, "", "   "):
        assert len(await repo.list(after=None, limit=10, q=q)) == 2


async def test_list_q_combines_with_after_limit_and_deletion(
    make_collection: MakeCollection,
) -> None:
    """`q` composes with keyset paging and still hides deleted collections."""
    repo = InMemoryCollectionRepository()
    made = [make_collection(f"Tape {n}") for n in range(4)]
    for collection in made:
        await repo.add(collection)
    await repo.add(make_collection("Vinyl"))
    made[3].soft_delete()
    await repo.save(made[3])

    first = await repo.list(after=None, limit=2, q="tape")
    rest = await repo.list(after=first[-1].id, limit=2, q="tape")

    assert first == made[:2]
    assert rest == [made[2]]


async def test_list_q_ignores_accents_both_ways(
    make_collection: MakeCollection,
) -> None:
    """Accented stored text matches plain `q`, and plain text matches accented `q`."""
    repo = InMemoryCollectionRepository()
    accented = make_collection("Café")
    described = make_collection("Other")
    described.description = "Crème"
    plain = make_collection("Cafe plain")
    percent = make_collection("50% café")
    miss = make_collection("Vinyl")
    for collection in (accented, described, plain, percent, miss):
        await repo.add(collection)

    async def ids(q: str) -> set[object]:
        return {c.id for c in await repo.list(after=None, limit=10, q=q)}

    assert await ids("cafe") == {accented.id, plain.id, percent.id}
    assert await ids("CAFÉ") == {accented.id, plain.id, percent.id}
    assert await ids("creme") == {described.id}
    assert await ids("50% cafe") == {percent.id}
