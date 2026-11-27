import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.graph.adapters.persistence.node_type_repository import (
    SqlAlchemyNodeTypeRepository,
)
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.paging import Cursor, PageRequest, SortOrder

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "cover_file": {
            "title": "Cover file",
            "type": "string",
            "allOf": [{"pattern": "^cover-"}, {"pattern": r"\.jpg$"}],
            "x-menagerist": {"kind": "text"},
        },
        "label": {"title": "Label", "type": "string", "pattern": "^café 🎵"},
    },
}


async def test_constraint_patterns_round_trip_through_jsonb(
    db_session: AsyncSession,
) -> None:
    """Backslashes, unicode and `allOf` order survive the JSONB column unchanged."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    node_type = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="record", label="Record")
    node_type.attributes_schema = _SCHEMA
    await repository.add(node_type)
    await db_session.flush()
    db_session.expire_all()

    stored = await repository.get(node_type.id, scope=ContentFilter.everyone())

    assert stored is not None
    assert stored.attributes_schema == _SCHEMA
    cover = stored.attributes_schema["properties"]["cover_file"]
    assert [p["pattern"] for p in cover["allOf"]] == ["^cover-", r"\.jpg$"]


async def test_slug_can_be_reused_after_soft_delete(db_session: AsyncSession) -> None:
    """A soft-deleted node type stops reserving its slug."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    first = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="record", label="Record")
    await repository.add(first)
    first.soft_delete()
    await repository.save(first)

    second = NodeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="record", label="Record again"
    )
    await repository.add(second)

    live = await repository.get_by_slug("record", scope=ContentFilter.everyone())
    assert live is not None
    assert live.id == second.id


async def test_live_node_types_cannot_share_a_slug(db_session: AsyncSession) -> None:
    """The index backs the use case's check: two live types cannot share a slug."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    await repository.add(
        NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="record", label="Record")
    )

    with pytest.raises(IntegrityError):
        await repository.add(
            NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="record", label="Duplicate")
        )


async def test_icon_and_colour_round_trip_and_can_be_cleared(
    db_session: AsyncSession,
) -> None:
    """A type's icon and colour are stored, changed and cleared."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    node_type = NodeType.create(
        owner_id=SYSTEM_ACTOR.id,
        slug="record",
        label="Record",
        icon="disc-3",
        colour="violet",
    )
    await repository.add(node_type)
    await db_session.flush()
    db_session.expire_all()

    stored = await repository.get(node_type.id, scope=ContentFilter.everyone())
    assert stored is not None
    assert (stored.icon, stored.colour) == ("disc-3", "violet")

    stored.update(icon="music")
    stored.clear_colour()
    await repository.save(stored)
    await db_session.flush()
    db_session.expire_all()

    changed = await repository.get(node_type.id, scope=ContentFilter.everyone())
    assert changed is not None
    assert (changed.icon, changed.colour) == ("music", None)


async def test_a_parent_is_stored_read_back_and_cleared(
    db_session: AsyncSession,
) -> None:
    """The parent slug survives a round trip; clearing it makes the type top-level."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    poster = NodeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="poster", label="Poster", parent="memorabilia"
    )
    plain = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="book", label="Book")
    await repository.add(poster)
    await repository.add(plain)
    await db_session.flush()
    db_session.expire_all()

    scope = ContentFilter.everyone()
    stored = await repository.get(poster.id, scope=scope)
    other = await repository.get(plain.id, scope=scope)
    assert stored is not None
    assert other is not None
    assert (stored.parent, other.parent) == ("memorabilia", None)

    stored.clear_parent()
    await repository.save(stored)
    await db_session.flush()
    db_session.expire_all()

    cleared = await repository.get(poster.id, scope=scope)
    assert cleared is not None
    assert cleared.parent is None


async def test_list_subtypes_returns_only_live_subtypes_of_that_parent(
    db_session: AsyncSession,
) -> None:
    """Other parents' subtypes, top-level types and deleted subtypes are left out."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    poster = NodeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="poster", label="Poster", parent="memorabilia"
    )
    figure = NodeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="figure", label="Figure", parent="memorabilia"
    )
    gone = NodeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="print", label="Print", parent="memorabilia"
    )
    gone.soft_delete()
    elsewhere = NodeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="vinyl", label="Vinyl", parent="music-media"
    )
    top = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="memorabilia", label="Memo")
    for row in (poster, figure, gone, elsewhere, top):
        await repository.add(row)

    found = await repository.list_subtypes(
        "memorabilia", scope=ContentFilter.everyone()
    )

    first = await repository.page_subtypes(
        "memorabilia", scope=ContentFilter.everyone(), page=PageRequest(limit=1)
    )
    rest = await repository.page_subtypes(
        "memorabilia",
        scope=ContentFilter.everyone(),
        page=PageRequest(after=Cursor.after_id(poster.id)),
    )

    assert [str(t.slug) for t in found] == ["poster", "figure"]
    assert [str(t.slug) for t in first.items] == ["poster"]
    assert first.next is not None
    assert [str(t.slug) for t in rest.items] == ["figure"]
    assert rest.next is None


async def test_a_type_cannot_be_its_own_parent_in_the_database(
    db_session: AsyncSession,
) -> None:
    """The check constraint backs the domain rule."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    node_type = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="poster", label="Poster")
    node_type.parent = "poster"

    with pytest.raises(IntegrityError):
        await repository.add(node_type)


@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", [None, "slug", "label", "created_at", "updated_at"])
async def test_list_cursors_visit_every_node_type_once_in_order(
    db_session: AsyncSession, sort: str | None, order: SortOrder
) -> None:
    """Following `next` never repeats a type or skips one, whatever the sort."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    owner = uuid.uuid7()
    for slug, label in [("b", "B"), ("a", "a"), ("c", "C"), ("d", "b"), ("e", "A")]:
        await repository.add(NodeType.create(owner_id=owner, slug=slug, label=label))
    scope = ContentFilter.everyone()
    everything = (
        await repository.list(
            scope=scope, page=PageRequest(sort=sort, order=order, limit=100)
        )
    ).items

    seen: list[uuid.UUID] = []
    request = PageRequest(sort=sort, order=order, limit=2)
    while True:
        page = await repository.list(scope=scope, page=request)
        seen.extend(t.id for t in page.items)
        if page.next is None:
            break
        request = PageRequest(after=page.next, sort=sort, order=order, limit=2)

    assert seen == [t.id for t in everything]
    assert len(set(seen)) == 5


async def test_list_sorts_node_types_by_label_ignoring_case(
    db_session: AsyncSession,
) -> None:
    """`label` orders by `lower(label)`."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    owner = uuid.uuid7()
    for slug, label in [("x", "banana"), ("y", "Apple"), ("z", "cherry")]:
        await repository.add(NodeType.create(owner_id=owner, slug=slug, label=label))

    page = await repository.list(
        scope=ContentFilter.everyone(), page=PageRequest(sort="label")
    )

    assert [t.label for t in page.items] == ["Apple", "banana", "cherry"]


async def test_list_q_matches_label_slug_and_description_ignoring_case_and_accents(
    db_session: AsyncSession,
) -> None:
    """The filter reads three columns, and applies to subtypes as well."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    owner = uuid.uuid7()
    await repository.add(NodeType.create(owner_id=owner, slug="memo", label="Memo"))
    by_label = NodeType.create(owner_id=owner, slug="a", label="Café", parent="memo")
    by_slug = NodeType.create(owner_id=owner, slug="cafe-b", label="B")
    by_description = NodeType.create(
        owner_id=owner, slug="c", label="C", description="A small CAFÉ", parent="memo"
    )
    miss = NodeType.create(owner_id=owner, slug="d", label="D")
    for node_type in (by_label, by_slug, by_description, miss):
        await repository.add(node_type)
    scope = ContentFilter.everyone()
    request = PageRequest(limit=100)

    found = await repository.list(scope=scope, page=request, q="CAFE")
    subtypes = await repository.page_subtypes(
        "memo", scope=scope, page=request, q="cafe"
    )
    blank = await repository.list(scope=scope, page=request, q="  ")

    assert {t.id for t in found.items} == {
        by_label.id,
        by_slug.id,
        by_description.id,
    }
    assert {t.id for t in subtypes.items} == {by_label.id, by_description.id}
    assert len(blank.items) == 5


@pytest.mark.parametrize("slug_order", list(SortOrder))
@pytest.mark.parametrize("label_order", list(SortOrder))
@pytest.mark.parametrize("limit", [1, 2, 100])
async def test_list_sorts_by_two_keys_each_in_its_own_direction(
    db_session: AsyncSession,
    label_order: SortOrder,
    slug_order: SortOrder,
    limit: int,
) -> None:
    """Label then slug, in every pair of directions, resuming from each cursor."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    owner = uuid.uuid7()
    pairs = [("b", "B"), ("a", "a"), ("c", "C"), ("d", "b"), ("e", "A"), ("f", "b")]
    for slug, label in pairs:
        await repository.add(NodeType.create(owner_id=owner, slug=slug, label=label))
    scope = ContentFilter.everyone()

    def request(**options: object) -> PageRequest:
        return PageRequest(
            sort="label",
            order=label_order,
            then_by=(("slug", slug_order),),
            limit=limit,
            **options,  # type: ignore[arg-type]
        )

    by_slug = sorted(pairs, key=lambda p: p[0], reverse=slug_order is SortOrder.DESC)
    expected = [
        slug
        for slug, _ in sorted(
            by_slug,
            key=lambda p: p[1].lower(),
            reverse=label_order is SortOrder.DESC,
        )
    ]

    seen: list[str] = []
    page = await repository.list(scope=scope, page=request())
    while True:
        seen.extend(str(t.slug) for t in page.items)
        if page.next is None:
            break
        assert page.next.sort == ("label", "slug")
        assert page.next.order == (label_order, slug_order)
        page = await repository.list(scope=scope, page=request(after=page.next))

    assert seen == expected


async def test_list_counts_the_filtered_list_in_scope_on_every_page(
    db_session: AsyncSession,
) -> None:
    """`total` counts the owner's matching rows on every page and follows `q`."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    owner, other = uuid.uuid7(), uuid.uuid7()
    for slug in ("a", "b", "c", "d", "e"):
        await repository.add(
            NodeType.create(owner_id=owner, slug=slug, label=slug.upper())
        )
    await repository.add(NodeType.create(owner_id=other, slug="f", label="F"))
    scope = ContentFilter.of(owner)

    first = await repository.list(scope=scope, page=PageRequest(limit=2))
    assert first.next is not None
    second = await repository.list(
        scope=scope, page=PageRequest(after=first.next, limit=2)
    )
    searched = await repository.list(scope=scope, page=PageRequest(limit=1), q="a")
    nothing = await repository.list(scope=scope, page=PageRequest(limit=1), q="zebra")

    assert (first.total, second.total) == (5, 5)
    assert searched.total == 1
    assert nothing.total == 0
