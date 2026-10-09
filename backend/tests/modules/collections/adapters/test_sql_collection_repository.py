import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
    _to_model,
)
from app.modules.collections.domain.collection import Collection
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


def _collection(name: str = "Jazz", slug: str | None = None) -> Collection:
    """Create a collection with a slug derived from `name` unless given."""
    return Collection.create(
        name=name,
        slug=Slug(slug or name),
        owner_id=uuid.uuid7(),
        description="Records",
    )


async def test_round_trips_every_field(db_session: AsyncSession) -> None:
    """A stored collection reads back with all its fields."""
    repo = SqlAlchemyCollectionRepository(db_session)
    collection = _collection()
    await repo.add(collection)
    db_session.expire_all()

    stored = await repo.get(collection.id)

    assert stored is not None
    assert (stored.name, stored.slug, stored.description) == (
        "Jazz",
        Slug("jazz"),
        "Records",
    )
    assert (stored.kind, stored.visibility, stored.owner_id) == (
        collection.kind,
        collection.visibility,
        collection.owner_id,
    )
    assert stored.created_at == collection.created_at
    assert stored.deleted_at is None


async def test_unknown_lookups_return_none(db_session: AsyncSession) -> None:
    """Unknown ids and slugs yield `None`."""
    repo = SqlAlchemyCollectionRepository(db_session)

    assert await repo.get(uuid.uuid7()) is None
    assert await repo.get_by_slug("nope") is None


async def test_save_persists_rename_and_soft_delete(db_session: AsyncSession) -> None:
    """Saved changes show; a saved soft delete hides the collection everywhere."""
    repo = SqlAlchemyCollectionRepository(db_session)
    collection = _collection()
    await repo.add(collection)
    collection.rename("Blues")
    await repo.save(collection)
    db_session.expire_all()
    stored = await repo.get(collection.id)
    assert stored is not None
    assert stored.name == "Blues"

    collection.soft_delete()
    await repo.save(collection)
    db_session.expire_all()

    assert await repo.get(collection.id) is None
    assert await repo.get_by_slug("jazz") is None
    assert await repo.list(after=None, limit=10) == []


async def test_list_is_ordered_by_id_with_keyset_paging(
    db_session: AsyncSession,
) -> None:
    """List orders by id and `after` resumes strictly past the given id."""
    repo = SqlAlchemyCollectionRepository(db_session)
    made = [_collection(f"Shelf {n}") for n in range(5)]
    for collection in reversed(made):
        await repo.add(collection)

    first = await repo.list(after=None, limit=2)
    assert [c.id for c in first] == [c.id for c in made[:2]]
    second = await repo.list(after=first[-1].id, limit=2)
    assert [c.id for c in second] == [c.id for c in made[2:4]]
    last = await repo.list(after=second[-1].id, limit=2)
    assert [c.id for c in last] == [c.id for c in made[4:]]
    assert await repo.list(after=last[-1].id, limit=2) == []


async def test_list_q_matches_name_or_description_ignoring_case(
    db_session: AsyncSession,
) -> None:
    """`q` keeps collections whose name or description contains it."""
    repo = SqlAlchemyCollectionRepository(db_session)
    by_name = _collection("Tapes")
    by_description = Collection.create(
        name="Other",
        slug=Slug("other"),
        owner_id=uuid.uuid7(),
        description="Old TAPE reels",
    )
    miss = _collection("Vinyl")
    for collection in (by_name, by_description, miss):
        await repo.add(collection)

    found = await repo.list(after=None, limit=10, q="tape")

    assert {c.id for c in found} == {by_name.id, by_description.id}


async def test_list_q_treats_wildcards_and_backslash_literally(
    db_session: AsyncSession,
) -> None:
    """Wildcards and backslashes in `q` match only themselves."""
    repo = SqlAlchemyCollectionRepository(db_session)
    percent = _collection("50% off")
    plain = _collection("500 things")
    underscore = _collection("a_b")
    other = _collection("axb")
    backslash = _collection("a\\b", slug="back")
    for collection in (percent, plain, underscore, other, backslash):
        await repo.add(collection)

    assert [c.id for c in await repo.list(after=None, limit=10, q="50%")] == [
        percent.id
    ]
    assert [c.id for c in await repo.list(after=None, limit=10, q="a_b")] == [
        underscore.id
    ]
    assert [c.id for c in await repo.list(after=None, limit=10, q="a\\b")] == [
        backslash.id
    ]


async def test_list_blank_q_returns_everything(db_session: AsyncSession) -> None:
    """`None`, empty and whitespace-only `q` apply no filter."""
    repo = SqlAlchemyCollectionRepository(db_session)
    await repo.add(_collection("A"))
    await repo.add(_collection("B"))

    for q in (None, "", "   "):
        assert len(await repo.list(after=None, limit=10, q=q)) == 2


async def test_list_q_combines_with_after_limit_and_deletion(
    db_session: AsyncSession,
) -> None:
    """`q` composes with keyset paging and still hides deleted collections."""
    repo = SqlAlchemyCollectionRepository(db_session)
    made = [_collection(f"Tape {n}") for n in range(4)]
    for collection in made:
        await repo.add(collection)
    await repo.add(_collection("Vinyl"))
    made[3].soft_delete()
    await repo.save(made[3])

    first = await repo.list(after=None, limit=2, q="tape")
    rest = await repo.list(after=first[-1].id, limit=2, q="tape")

    assert [c.id for c in first] == [c.id for c in made[:2]]
    assert [c.id for c in rest] == [made[2].id]


async def test_slug_reusable_after_soft_delete(db_session: AsyncSession) -> None:
    """The partial index frees a slug once its holder is soft deleted."""
    repo = SqlAlchemyCollectionRepository(db_session)
    old = _collection()
    await repo.add(old)
    old.soft_delete()
    await repo.save(old)
    new = _collection()
    await repo.add(new)

    found = await repo.get_by_slug("jazz")

    assert found is not None
    assert found.id == new.id


async def test_add_maps_duplicate_live_slug_to_conflict(
    db_session: AsyncSession,
) -> None:
    """A second live collection with the same slug raises `ConflictError`."""
    repo = SqlAlchemyCollectionRepository(db_session)
    first = _collection()
    await repo.add(first)

    with pytest.raises(ConflictError, match="slug 'jazz' already exists"):
        await repo.add(_collection())

    found = await repo.get_by_slug("jazz")
    assert found is not None
    assert found.id == first.id


async def test_index_rejects_two_live_rows_with_one_slug(
    db_session: AsyncSession,
) -> None:
    """The unique index itself, not only the mapping, rejects the duplicate."""
    db_session.add(_to_model(_collection()))
    db_session.add(_to_model(_collection()))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_list_q_ignores_accents_both_ways(db_session: AsyncSession) -> None:
    """Accented stored text matches plain `q`, and plain text matches accented `q`."""
    repo = SqlAlchemyCollectionRepository(db_session)
    accented = _collection("Café")
    described = Collection.create(
        name="Other", slug=Slug("other"), owner_id=uuid.uuid7(), description="Crème"
    )
    plain = _collection("Cafe plain", slug="plain")
    percent = _collection("50% café", slug="pct")
    miss = _collection("Vinyl", slug="vinyl")
    for collection in (accented, described, plain, percent, miss):
        await repo.add(collection)

    async def ids(q: str) -> set[uuid.UUID]:
        return {c.id for c in await repo.list(after=None, limit=10, q=q)}

    assert await ids("cafe") == {accented.id, plain.id, percent.id}
    assert await ids("CAFÉ") == {accented.id, plain.id, percent.id}
    assert await ids("creme") == {described.id}
    assert await ids("50% cafe") == {percent.id}
