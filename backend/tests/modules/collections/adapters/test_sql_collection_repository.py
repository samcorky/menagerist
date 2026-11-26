import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
    _to_model,
)
from app.modules.collections.adapters.persistence.models import CollectionModel
from app.modules.collections.domain.collection import Collection, CollectionKind
from app.platform.keyset import keyset_page, text_column
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.paging import Cursor, InvalidCursorError, PageRequest, SortOrder
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_OWNER = uuid.UUID(int=101)
pytestmark = pytest.mark.integration


def _collection(name: str = "Jazz", slug: str | None = None) -> Collection:
    """Create a collection with a slug derived from `name` unless given."""
    return Collection.create(
        name=name,
        slug=Slug(slug or name),
        owner_id=_OWNER,
        description="Records",
    )


async def test_round_trips_every_field(db_session: AsyncSession) -> None:
    """A stored collection reads back with all its fields."""
    repo = SqlAlchemyCollectionRepository(db_session)
    collection = _collection()
    await repo.add(collection)
    db_session.expire_all()

    stored = await repo.get(collection.id, scope=ContentFilter.everyone())

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

    assert await repo.get(uuid.uuid7(), scope=ContentFilter.everyone()) is None
    assert await repo.get_by_slug("nope", scope=ContentFilter.everyone()) is None


async def test_save_persists_rename_and_soft_delete(db_session: AsyncSession) -> None:
    """Saved changes show; a saved soft delete hides the collection everywhere."""
    repo = SqlAlchemyCollectionRepository(db_session)
    collection = _collection()
    await repo.add(collection)
    collection.rename("Blues")
    await repo.save(collection)
    db_session.expire_all()
    stored = await repo.get(collection.id, scope=ContentFilter.everyone())
    assert stored is not None
    assert stored.name == "Blues"

    collection.soft_delete()
    await repo.save(collection)
    db_session.expire_all()

    assert await repo.get(collection.id, scope=ContentFilter.everyone()) is None
    assert await repo.get_by_slug("jazz", scope=ContentFilter.everyone()) is None
    assert (
        await repo.list(scope=ContentFilter.everyone(), page=PageRequest(limit=10))
    ).items == []


async def test_list_is_ordered_by_id_with_keyset_paging(
    db_session: AsyncSession,
) -> None:
    """List orders by id and `after` resumes strictly past the given id."""
    repo = SqlAlchemyCollectionRepository(db_session)
    made = [_collection(f"Shelf {n}") for n in range(5)]
    for collection in reversed(made):
        await repo.add(collection)

    first = (
        await repo.list(scope=ContentFilter.everyone(), page=PageRequest(limit=2))
    ).items
    assert [c.id for c in first] == [c.id for c in made[:2]]
    second = (
        await repo.list(
            scope=ContentFilter.everyone(),
            page=PageRequest(after=Cursor.after_id(first[-1].id), limit=2),
        )
    ).items
    assert [c.id for c in second] == [c.id for c in made[2:4]]
    last = (
        await repo.list(
            scope=ContentFilter.everyone(),
            page=PageRequest(after=Cursor.after_id(second[-1].id), limit=2),
        )
    ).items
    assert [c.id for c in last] == [c.id for c in made[4:]]
    assert (
        await repo.list(
            scope=ContentFilter.everyone(),
            page=PageRequest(after=Cursor.after_id(last[-1].id), limit=2),
        )
    ).items == []


async def test_list_q_matches_name_or_description_ignoring_case(
    db_session: AsyncSession,
) -> None:
    """`q` keeps collections whose name or description contains it."""
    repo = SqlAlchemyCollectionRepository(db_session)
    by_name = _collection("Tapes")
    by_description = Collection.create(
        name="Other",
        slug=Slug("other"),
        owner_id=_OWNER,
        description="Old TAPE reels",
    )
    miss = _collection("Vinyl")
    for collection in (by_name, by_description, miss):
        await repo.add(collection)

    found = (
        await repo.list(
            scope=ContentFilter.everyone(), q="tape", page=PageRequest(limit=10)
        )
    ).items

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

    assert [
        c.id
        for c in (
            await repo.list(
                scope=ContentFilter.everyone(), q="50%", page=PageRequest(limit=10)
            )
        ).items
    ] == [percent.id]
    assert [
        c.id
        for c in (
            await repo.list(
                scope=ContentFilter.everyone(), q="a_b", page=PageRequest(limit=10)
            )
        ).items
    ] == [underscore.id]
    assert [
        c.id
        for c in (
            await repo.list(
                scope=ContentFilter.everyone(), q="a\\b", page=PageRequest(limit=10)
            )
        ).items
    ] == [backslash.id]


async def test_list_blank_q_returns_everything(db_session: AsyncSession) -> None:
    """`None`, empty and whitespace-only `q` apply no filter."""
    repo = SqlAlchemyCollectionRepository(db_session)
    await repo.add(_collection("A"))
    await repo.add(_collection("B"))

    for q in (None, "", "   "):
        assert (
            len(
                (
                    await repo.list(
                        scope=ContentFilter.everyone(), q=q, page=PageRequest(limit=10)
                    )
                ).items
            )
            == 2
        )


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

    first = (
        await repo.list(
            scope=ContentFilter.everyone(), q="tape", page=PageRequest(limit=2)
        )
    ).items
    rest = (
        await repo.list(
            scope=ContentFilter.everyone(),
            q="tape",
            page=PageRequest(after=Cursor.after_id(first[-1].id), limit=2),
        )
    ).items

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

    found = await repo.get_by_slug("jazz", scope=ContentFilter.everyone())

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

    found = await repo.get_by_slug("jazz", scope=ContentFilter.everyone())
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
        name="Other", slug=Slug("other"), owner_id=_OWNER, description="Crème"
    )
    plain = _collection("Cafe plain", slug="plain")
    percent = _collection("50% café", slug="pct")
    miss = _collection("Vinyl", slug="vinyl")
    for collection in (accented, described, plain, percent, miss):
        await repo.add(collection)

    async def ids(q: str) -> set[uuid.UUID]:
        return {
            c.id
            for c in (
                await repo.list(
                    scope=ContentFilter.everyone(), q=q, page=PageRequest(limit=10)
                )
            ).items
        }

    assert await ids("cafe") == {accented.id, plain.id, percent.id}
    assert await ids("CAFÉ") == {accented.id, plain.id, percent.id}
    assert await ids("creme") == {described.id}
    assert await ids("50% cafe") == {percent.id}


async def test_definition_round_trips_nested_json(db_session: AsyncSession) -> None:
    """A dynamic collection keeps its nested definition and kind."""
    repo = SqlAlchemyCollectionRepository(db_session)
    definition = {"op": "and", "conditions": [{"v": [1, "x", None, {"k": True}]}]}
    smart = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=_OWNER, definition=definition
    )
    await repo.add(smart)
    db_session.expire_all()

    stored = await repo.get(smart.id, scope=ContentFilter.everyone())

    assert stored is not None
    assert stored.kind is CollectionKind.DYNAMIC
    assert stored.definition == definition


async def test_manual_collection_has_no_definition(db_session: AsyncSession) -> None:
    """A manual collection reads back with a null definition and manual kind."""
    repo = SqlAlchemyCollectionRepository(db_session)
    plain = _collection()
    await repo.add(plain)
    db_session.expire_all()

    stored = await repo.get(plain.id, scope=ContentFilter.everyone())

    assert stored is not None
    assert stored.kind is CollectionKind.MANUAL
    assert stored.definition is None


async def test_saving_replaced_definition_persists(db_session: AsyncSession) -> None:
    """A replaced definition is written by `save`."""
    repo = SqlAlchemyCollectionRepository(db_session)
    smart = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=_OWNER, definition={"a": 1}
    )
    await repo.add(smart)
    smart.replace_definition({"b": [2]})
    await repo.save(smart)
    db_session.expire_all()

    stored = await repo.get(smart.id, scope=ContentFilter.everyone())

    assert stored is not None
    assert stored.definition == {"b": [2]}


async def test_save_maps_a_slug_taken_meanwhile_to_conflict(
    db_session: AsyncSession,
) -> None:
    """A rename onto a slug another request just took is a 409, not a 500."""
    repo = SqlAlchemyCollectionRepository(db_session)
    holder = _collection("Jazz")
    mover = _collection("Blues")
    await repo.add(holder)
    await repo.add(mover)
    mover.rename_slug(Slug("jazz"))

    with pytest.raises(ConflictError, match="slug 'jazz' already exists"):
        await repo.save(mover)

    # The session survives the rejected flush.
    db_session.expire_all()
    found = await repo.get_by_slug("blues", scope=ContentFilter.everyone())
    assert found is not None
    assert found.id == mover.id


async def test_list_filters_by_kind(db_session: AsyncSession) -> None:
    """`kind` keeps only manual or only smart collections, with paging intact."""
    repo = SqlAlchemyCollectionRepository(db_session)
    manual = [_collection(f"Shelf {n}") for n in range(3)]
    smart = [
        Collection.create(
            name=f"Smart {n}",
            slug=Slug(f"smart-{n}"),
            owner_id=_OWNER,
            definition={"v": 1},
        )
        for n in range(2)
    ]
    for collection in (*manual, *smart):
        await repo.add(collection)
    everyone = ContentFilter.everyone()

    manual_ids = [
        c.id
        for c in (
            await repo.list(
                scope=everyone, kind=CollectionKind.MANUAL, page=PageRequest(limit=10)
            )
        ).items
    ]
    smart_ids = [
        c.id
        for c in (
            await repo.list(
                scope=everyone, kind=CollectionKind.DYNAMIC, page=PageRequest(limit=10)
            )
        ).items
    ]
    paged = (
        await repo.list(
            scope=everyone, kind=CollectionKind.MANUAL, page=PageRequest(limit=2)
        )
    ).items

    assert manual_ids == sorted(c.id for c in manual)
    assert smart_ids == sorted(c.id for c in smart)
    assert [c.id for c in paged] == manual_ids[:2]
    assert len((await repo.list(scope=everyone, page=PageRequest(limit=10))).items) == 5


async def _names(
    repo: SqlAlchemyCollectionRepository, page: PageRequest, **filters: object
) -> list[str]:
    """The names on one page of `repo.list` for everyone."""
    found = await repo.list(scope=ContentFilter.everyone(), page=page, **filters)  # type: ignore[arg-type]
    return [c.name for c in found.items]


async def test_list_sorts_by_name_ignoring_case_in_both_directions(
    db_session: AsyncSession,
) -> None:
    """`name` orders by `lower(name)`, and `desc` reverses it."""
    repo = SqlAlchemyCollectionRepository(db_session)
    for name in ["banana", "Apple", "cherry", "apricot"]:
        await repo.add(_collection(name))

    ascending = await _names(repo, PageRequest(sort="name"))
    descending = await _names(repo, PageRequest(sort="name", order=SortOrder.DESC))

    assert ascending == ["Apple", "apricot", "banana", "cherry"]
    assert descending == ["cherry", "banana", "apricot", "Apple"]


async def test_list_sorts_by_created_and_updated_time(db_session: AsyncSession) -> None:
    """Timestamps sort by value; renaming moves a collection in `updated_at`."""
    repo = SqlAlchemyCollectionRepository(db_session)
    first, second, third = (_collection(n) for n in ["One", "Two", "Three"])
    for collection in (first, second, third):
        await repo.add(collection)
    first.rename("One again")
    await repo.save(first)

    created = await _names(repo, PageRequest(sort="created_at", order=SortOrder.DESC))
    updated = await _names(repo, PageRequest(sort="updated_at"))

    assert created == ["Three", "Two", "One again"]
    assert updated == ["Two", "Three", "One again"]


@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", [None, "name", "created_at", "updated_at"])
async def test_list_cursors_visit_every_row_once_in_order(
    db_session: AsyncSession, sort: str | None, order: SortOrder
) -> None:
    """Following `next` never repeats a row or skips one, and ties keep their order."""
    repo = SqlAlchemyCollectionRepository(db_session)
    for n, name in enumerate(["b", "A", "b", "c", "B", "a", "c"]):
        await repo.add(_collection(name, slug=f"s{n}"))
    everything = (
        await repo.list(
            scope=ContentFilter.everyone(),
            page=PageRequest(sort=sort, order=order, limit=100),
        )
    ).items

    seen: list[uuid.UUID] = []
    request = PageRequest(sort=sort, order=order, limit=2)
    while True:
        page = await repo.list(scope=ContentFilter.everyone(), page=request)
        seen.extend(c.id for c in page.items)
        if page.next is None:
            break
        request = PageRequest(after=page.next, sort=sort, order=order, limit=2)

    assert seen == [c.id for c in everything]
    assert len(set(seen)) == 7


async def test_list_cursors_stay_inside_the_scope(db_session: AsyncSession) -> None:
    """Paging never reaches a collection the scope leaves out."""
    repo = SqlAlchemyCollectionRepository(db_session)
    mine = Collection.create(name="Mine", slug=Slug("mine"), owner_id=_OWNER)
    other = Collection.create(
        name="Theirs", slug=Slug("theirs"), owner_id=uuid.UUID(int=202)
    )
    await repo.add(mine)
    await repo.add(other)
    scope = ContentFilter(user_id=_OWNER)
    before_everything = Cursor(
        sort=("name",), order=(SortOrder.ASC,), values=("",), id=uuid.UUID(int=0)
    )

    rest = await repo.list(
        scope=scope, page=PageRequest(after=before_everything, sort="name", limit=10)
    )

    assert [c.name for c in rest.items] == ["Mine"]
    assert rest.next is None


async def test_list_a_cursor_value_of_the_wrong_kind_is_refused(
    db_session: AsyncSession,
) -> None:
    """A forged cursor whose value the key cannot compare with is a 400, not a 500."""
    repo = SqlAlchemyCollectionRepository(db_session)
    await repo.add(_collection())
    forged = Cursor(
        sort=("created_at",),
        order=(SortOrder.ASC,),
        values=(7,),
        id=uuid.uuid7(),
    )

    with pytest.raises(InvalidCursorError):
        await repo.list(
            scope=ContentFilter.everyone(),
            page=PageRequest(after=forged, sort="created_at"),
        )


async def test_list_a_cursor_from_another_sort_is_refused(
    db_session: AsyncSession,
) -> None:
    """The cursor must match the request's sort and order."""
    repo = SqlAlchemyCollectionRepository(db_session)
    await repo.add(_collection("A", slug="a"))
    await repo.add(_collection("B", slug="b"))
    first = await repo.list(
        scope=ContentFilter.everyone(), page=PageRequest(sort="name", limit=1)
    )

    with pytest.raises(InvalidCursorError):
        await repo.list(
            scope=ContentFilter.everyone(), page=PageRequest(after=first.next)
        )


async def test_keyset_page_puts_empty_values_last_in_both_directions(
    db_session: AsyncSession,
) -> None:
    """Rows with no description follow the rest, whichever way the list runs."""
    repo = SqlAlchemyCollectionRepository(db_session)
    for n, description in enumerate([None, "b", None, "a"]):
        await repo.add(
            Collection.create(
                name=f"C{n}",
                slug=Slug(f"c{n}"),
                owner_id=_OWNER,
                description=description,
            )
        )
    columns = {"description": text_column(CollectionModel.description)}

    async def names(order: SortOrder, limit: int) -> list[str]:
        out: list[str] = []
        request = PageRequest(sort="description", order=order, limit=limit)
        while True:
            page = await keyset_page(
                db_session,
                select(CollectionModel),
                id_column=CollectionModel.id,
                columns=columns,
                request=request,
                to_domain=lambda model: model.name,
            )
            out.extend(page.items)
            if page.next is None:
                return out
            request = PageRequest(
                after=page.next, sort="description", order=order, limit=limit
            )

    assert await names(SortOrder.ASC, 1) == ["C3", "C1", "C0", "C2"]
    assert await names(SortOrder.DESC, 3) == ["C1", "C3", "C2", "C0"]


@pytest.mark.parametrize("limit", [-1, 0])
async def test_list_a_limit_below_one_returns_no_rows_instead_of_failing(
    db_session: AsyncSession, limit: int
) -> None:
    """The page size is clamped, so a negative limit is not sent to the database."""
    repo = SqlAlchemyCollectionRepository(db_session)
    await repo.add(_collection("A", slug="a"))

    page = await repo.list(
        scope=ContentFilter.everyone(), page=PageRequest(limit=limit)
    )

    assert page.items == []
    assert page.next is None
