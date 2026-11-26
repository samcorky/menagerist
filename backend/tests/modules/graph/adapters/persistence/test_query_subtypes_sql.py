"""The SQL evaluator agrees with the in-memory one on parent and subtype queries (#768).

These are the cases of `application/test_query_subtypes.py`, run on Postgres.
"""

from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.graph.ports.unit_of_work import GraphRepos

pytestmark = pytest.mark.integration

TODAY = date(2026, 11, 25)
SCOPE = ContentFilter.everyone()


def _text(title: str) -> dict[str, Any]:
    return {"type": "string", "title": title, "x-menagerist": {"kind": "text"}}


def _schema(**props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props}


async def _world(db_session: AsyncSession) -> GraphRepos:
    repos = build_graph_repos(db_session)
    types = (
        ("memorabilia", None, _schema(condition=_text("Condition"))),
        ("poster", "memorabilia", _schema(width=_text("Width"))),
        ("figure", "memorabilia", _schema(height=_text("Height"))),
        ("film", None, _schema(condition=_text("Condition"))),
    )
    for slug, parent, schema in types:
        await repos.node_types.add(
            NodeType.create(
                owner_id=SYSTEM_ACTOR.id,
                slug=slug,
                label=slug.title(),
                attributes_schema=schema,
                parent=parent,
            )
        )
    items: tuple[tuple[str, str | None, dict[str, Any]], ...] = (
        ("Base", "memorabilia", {"condition": "b"}),
        ("Alien poster", "poster", {"condition": "a", "width": "27"}),
        ("Zeta poster", "poster", {"condition": "c"}),
        ("Xeno figure", "figure", {"condition": "d", "height": "9"}),
        ("Alien film", "film", {"condition": "e"}),
        ("Loose", None, {}),
    )
    for name, item_type, attributes in items:
        await repos.nodes.add(
            Node.create(
                owner_id=SYSTEM_ACTOR.id,
                name=name,
                type=item_type,
                attributes=attributes,
            )
        )
    await db_session.flush()
    return repos


def _query(*children: dict[str, Any], **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    where = {"op": "and", "children": list(children)} if children else None
    return {"v": 1, "where": where, **extra}


def _type(*slugs: str, mode: str = "any") -> dict[str, Any]:
    leaf: dict[str, Any] = {"kind": "type", "mode": mode}
    if slugs:
        leaf["in"] = list(slugs)
    return leaf


def _field(type_slug: str, key: str, op: str, value: str) -> dict[str, Any]:
    return {"kind": "field", "type": type_slug, "key": key, "op": op, "value": value}


async def _names(repos: GraphRepos, raw: dict[str, Any]) -> list[str]:
    resolved, _ = await prepare_query(repos, raw, TODAY, scope=SCOPE)
    hits = await repos.nodes.search(
        scope=SCOPE, resolved=resolved, after=None, limit=50
    )
    return [hit.node.name for hit in hits]


async def test_a_parent_matches_its_subtypes_and_a_subtype_only_itself(
    db_session: AsyncSession,
) -> None:
    """Is type and is none of, on a parent and on a subtype."""
    repos = await _world(db_session)

    parent = await _names(repos, _query(_type("memorabilia")))
    subtype = await _names(repos, _query(_type("poster")))
    none_of = await _names(repos, _query(_type("memorabilia", mode="none")))
    any_type = await _names(repos, _query(_type()))
    untyped = await _names(repos, _query(_type(mode="none")))

    assert sorted(parent) == ["Alien poster", "Base", "Xeno figure", "Zeta poster"]
    assert sorted(subtype) == ["Alien poster", "Zeta poster"]
    assert sorted(none_of) == ["Alien film", "Loose"]
    assert "Loose" not in any_type
    assert untyped == ["Loose"]


async def test_field_conditions_and_sorting_reach_the_subtypes(
    db_session: AsyncSession,
) -> None:
    """A parent's field matches and orders its subtypes' items; a subtype may use it."""
    repos = await _world(db_session)
    sort = [{"by": "field", "type": "memorabilia", "key": "condition", "dir": "desc"}]

    on_parent = await _names(
        repos, _query(_field("memorabilia", "condition", "!=", "e"))
    )
    on_subtype = await _names(repos, _query(_field("poster", "condition", "=", "a")))
    negated = await _names(
        repos,
        {
            "v": 1,
            "where": {
                "op": "not",
                "children": [_field("memorabilia", "condition", "=", "a")],
            },
        },
    )
    ordered = await _names(repos, _query(_type("memorabilia"), sort=sort))

    assert sorted(on_parent) == ["Alien poster", "Base", "Xeno figure", "Zeta poster"]
    assert on_subtype == ["Alien poster"]
    assert "Alien poster" not in negated
    assert {"Base", "Zeta poster", "Xeno figure"} <= set(negated)
    assert ordered == ["Xeno figure", "Zeta poster", "Base", "Alien poster"]
