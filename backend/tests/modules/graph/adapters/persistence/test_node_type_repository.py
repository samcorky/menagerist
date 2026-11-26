from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.graph.adapters.persistence.node_type_repository import (
    SqlAlchemyNodeTypeRepository,
)
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

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

    first = await repository.list_subtypes(
        "memorabilia", scope=ContentFilter.everyone(), limit=1
    )
    rest = await repository.list_subtypes(
        "memorabilia", scope=ContentFilter.everyone(), after=poster.id
    )

    assert [str(t.slug) for t in found] == ["poster", "figure"]
    assert [str(t.slug) for t in first] == ["poster"]
    assert [str(t.slug) for t in rest] == ["figure"]


async def test_a_type_cannot_be_its_own_parent_in_the_database(
    db_session: AsyncSession,
) -> None:
    """The check constraint backs the domain rule."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    node_type = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="poster", label="Poster")
    node_type.parent = "poster"

    with pytest.raises(IntegrityError):
        await repository.add(node_type)
