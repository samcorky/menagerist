"""Moving a shared field up to a parent on Postgres changes no item (#774)."""

import copy
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.graph.adapters.persistence.unit_of_work import (
    build_graph_repos,
    create_in_memory_graph_uow,
)
from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.application.list_shared_subtype_fields import (
    ListSharedSubtypeFields,
    ListSharedSubtypeFieldsQuery,
)
from app.modules.graph.application.parent_type import resolve_effective_schema
from app.modules.graph.application.promote_subtype_field import (
    PromoteSubtypeField,
    PromoteSubtypeFieldCommand,
)
from app.modules.graph.domain.errors import InvalidSchemaError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.graph.ports.unit_of_work import GraphRepos

pytestmark = pytest.mark.integration

EVERYONE = ContentFilter.everyone()
VALUES = {"condition": "Good", "width": "27 in", "value": "high"}


def _condition(*options: str) -> dict[str, Any]:
    return {
        "type": "string",
        "title": "Condition",
        "enum": list(options),
        "x-menagerist": {"kind": "choice"},
    }


async def _world(session: AsyncSession) -> tuple[GraphRepos, NodeType, Node]:
    repos = build_graph_repos(session)
    memo = NodeType.create(
        owner_id=SYSTEM_ACTOR.id,
        slug="memorabilia",
        label="Memorabilia",
        attributes_schema={
            "type": "object",
            "properties": {
                "value": {"type": "string", "x-menagerist": {"kind": "text"}}
            },
        },
    )
    types = [
        memo,
        NodeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug="poster",
            label="Poster",
            parent="memorabilia",
            attributes_schema={
                "type": "object",
                "properties": {
                    "condition": _condition("Mint", "Good"),
                    "width": {"type": "string", "x-menagerist": {"kind": "text"}},
                },
                "x-menagerist": {"required": ["condition"]},
            },
        ),
        NodeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug="print",
            label="Print",
            parent="memorabilia",
            attributes_schema={
                "type": "object",
                "properties": {"condition": _condition("Fair", "Mint")},
            },
        ),
    ]
    for node_type in types:
        await repos.node_types.add(node_type)
    item = Node.create(
        owner_id=SYSTEM_ACTOR.id, name="Alien", type="poster", attributes=dict(VALUES)
    )
    await repos.nodes.add(item)
    await session.flush()
    return repos, memo, item


async def _stored(repos: GraphRepos, session: AsyncSession, slug: str) -> NodeType:
    await session.flush()
    session.expire_all()
    found = await repos.node_types.get_by_slug(slug, scope=EVERYONE)
    assert found is not None
    return found


async def test_promoting_reads_back_from_the_database_and_leaves_items_alone(
    db_session: AsyncSession,
) -> None:
    """The field is above, gone below, and the item holds and validates the same."""
    repos, memo, item = await _world(db_session)
    uow = create_in_memory_graph_uow(repos)

    listed = await ListSharedSubtypeFields(repos, InMemoryAccessGuard()).handle(
        ListSharedSubtypeFieldsQuery(node_type_id=memo.id), SYSTEM_ACTOR
    )
    assert [(f.key, f.subtypes) for f in listed] == [("condition", ("poster", "print"))]

    promoted = await PromoteSubtypeField(uow, InMemoryAccessGuard()).handle(
        PromoteSubtypeFieldCommand(node_type_id=memo.id, key="condition"), SYSTEM_ACTOR
    )

    assert promoted.subtypes == 2
    parent = await _stored(repos, db_session, "memorabilia")
    properties = (parent.attributes_schema or {})["properties"]
    assert list(properties) == ["value", "condition"]
    assert properties["condition"]["enum"] == ["Mint", "Good", "Fair"]
    assert (parent.attributes_schema or {})["x-menagerist"]["required"] == ["condition"]
    for slug in ("poster", "print"):
        sub = await _stored(repos, db_session, slug)
        assert "condition" not in (sub.attributes_schema or {}).get("properties", {})
    db_session.expire_all()
    stored_item = await repos.nodes.get(item.id, scope=EVERYONE)
    assert stored_item is not None
    assert stored_item.attributes == VALUES
    poster = await _stored(repos, db_session, "poster")
    schema = await resolve_effective_schema(repos, poster, scope=EVERYONE)
    assert schema is not None
    validate_attributes(schema, stored_item.attributes)


async def test_a_refused_promotion_writes_nothing(db_session: AsyncSession) -> None:
    """A subtype keeping the key as another kind stops it; every type is as it was."""
    repos, memo, _ = await _world(db_session)
    await repos.node_types.add(
        NodeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug="mug",
            label="Mug",
            parent="memorabilia",
            attributes_schema={
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "number",
                        "title": "Condition",
                        "x-menagerist": {"kind": "number"},
                    }
                },
            },
        )
    )
    await db_session.flush()
    before = {
        slug: copy.deepcopy((await _stored(repos, db_session, slug)).attributes_schema)
        for slug in ("memorabilia", "poster", "print", "mug")
    }
    uow = create_in_memory_graph_uow(repos)

    with pytest.raises(InvalidSchemaError, match="1 subtype keeps Condition"):
        await PromoteSubtypeField(uow, InMemoryAccessGuard()).handle(
            PromoteSubtypeFieldCommand(node_type_id=memo.id, key="condition"),
            SYSTEM_ACTOR,
        )

    for slug, schema in before.items():
        assert (await _stored(repos, db_session, slug)).attributes_schema == schema
