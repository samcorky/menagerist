"""Filtering by a parent includes its subtypes; filtering by a subtype does not (#768).

The tests run the same queries through both evaluators: the in-memory repository
here, and (in the integration test next door) Postgres.
"""

import uuid
from datetime import date
from typing import Any

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_external_conditions import (
    InMemoryExternalConditions,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.content_filter import ContentFilter

ME = uuid.UUID(int=1)
TODAY = date(2026, 11, 25)
SCOPE = ContentFilter.of(ME)


def _text(title: str) -> dict[str, Any]:
    return {"type": "string", "title": title, "x-menagerist": {"kind": "text"}}


def _schema(**props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props}


async def _world() -> GraphRepos:
    """Memorabilia with Poster and Figure beneath it, a stand-alone Film, no type."""
    provider = InMemoryExternalConditions()
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(provider),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
        external=provider,
        definitions=provider,
    )
    repos_types = (
        ("memorabilia", None, _schema(condition=_text("Condition"))),
        ("poster", "memorabilia", _schema(width=_text("Width"))),
        ("figure", "memorabilia", _schema(height=_text("Height"))),
        ("film", None, _schema(condition=_text("Condition"))),
    )
    for slug, parent, schema in repos_types:
        await repos.node_types.add(
            NodeType.create(
                owner_id=ME,
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
            Node.create(owner_id=ME, name=name, type=item_type, attributes=attributes)
        )
    return repos


def _query(*children: dict[str, Any], **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    where = {"op": "and", "children": list(children)} if children else None
    return {"v": 1, "where": where, **extra}


def _type(*slugs: str, mode: str = "any") -> dict[str, Any]:
    """A type condition; naming no types means every type."""
    leaf: dict[str, Any] = {"kind": "type", "mode": mode}
    if slugs:
        leaf["in"] = list(slugs)
    return leaf


def _field(type_slug: str, key: str, op: str, value: str = "") -> dict[str, Any]:
    leaf: dict[str, Any] = {"kind": "field", "type": type_slug, "key": key, "op": op}
    if value:
        leaf["value"] = value
    return leaf


async def _names(repos: GraphRepos, raw: dict[str, Any]) -> list[str]:
    resolved, _ = await prepare_query(repos, raw, TODAY, scope=SCOPE)
    hits = await repos.nodes.search(
        scope=SCOPE, resolved=resolved, after=None, limit=50
    )
    return [hit.node.name for hit in hits]


async def test_a_parent_type_matches_its_subtypes_items() -> None:
    """Is type on the parent finds its own, its posters and its figures."""
    repos = await _world()

    found = await _names(repos, _query(_type("memorabilia")))

    assert sorted(found) == ["Alien poster", "Base", "Xeno figure", "Zeta poster"]


async def test_a_subtype_matches_only_itself() -> None:
    """Filtering by a subtype finds neither its parent's nor its sibling's items."""
    repos = await _world()

    assert sorted(await _names(repos, _query(_type("poster")))) == [
        "Alien poster",
        "Zeta poster",
    ]


async def test_is_not_one_of_a_parent_excludes_its_subtypes_and_keeps_untyped() -> None:
    """None of memorabilia leaves the film and the untyped item."""
    repos = await _world()

    found = await _names(repos, _query(_type("memorabilia", mode="none")))

    assert sorted(found) == ["Alien film", "Loose"]


async def test_has_an_item_type_still_means_any_type_and_has_none_means_untyped() -> (
    None
):
    """With no types named nothing is expanded."""
    repos = await _world()

    assert "Loose" not in await _names(repos, _query(_type()))
    assert await _names(repos, _query(_type(mode="none"))) == ["Loose"]


async def test_a_field_condition_on_the_parent_reaches_its_subtypes() -> None:
    """A parent's field matches the items of every subtype that inherits it."""
    repos = await _world()

    found = await _names(repos, _query(_field("memorabilia", "condition", "!=", "e")))

    assert sorted(found) == ["Alien poster", "Base", "Xeno figure", "Zeta poster"]


async def test_a_field_condition_on_a_subtype_reaches_an_inherited_field() -> None:
    """A subtype's own condition may name a field it inherits."""
    repos = await _world()

    found = await _names(repos, _query(_field("poster", "condition", "=", "a")))

    assert found == ["Alien poster"]


async def test_a_negated_condition_on_the_parent_still_covers_the_subtypes() -> None:
    """Not (condition is a) on the parent finds every other memorabilia item."""
    repos = await _world()
    inner = _field("memorabilia", "condition", "=", "a")

    found = await _names(repos, {"v": 1, "where": {"op": "not", "children": [inner]}})

    assert "Alien poster" not in found
    assert {"Base", "Zeta poster", "Xeno figure"} <= set(found)


async def test_sorting_by_a_parents_field_orders_its_subtypes_items() -> None:
    """The sort key on the parent's field is read from the subtypes' items too."""
    repos = await _world()
    sort = [{"by": "field", "type": "memorabilia", "key": "condition", "dir": "desc"}]

    found = await _names(repos, _query(_type("memorabilia"), sort=sort))

    assert found == ["Xeno figure", "Zeta poster", "Base", "Alien poster"]


async def test_a_smart_collection_follows_a_subtype_added_later() -> None:
    """The stored search names the parent; a new subtype's items join it unsaved."""
    repos = await _world()
    provider = repos.definitions
    assert isinstance(provider, InMemoryExternalConditions)
    collection = uuid.UUID(int=0xE0001)
    provider.add_collection(
        collection, owner_id=ME, definition=_query(_type("memorabilia"))
    )
    ask = _query({"kind": "collection", "mode": "any", "in": [str(collection)]})
    before = await _names(repos, ask)

    await repos.node_types.add(
        NodeType.create(
            owner_id=ME,
            slug="mug",
            label="Mug",
            attributes_schema=_schema(),
            parent="memorabilia",
        )
    )
    await repos.nodes.add(Node.create(owner_id=ME, name="Alien mug", type="mug"))

    after = await _names(repos, ask)

    assert "Alien mug" not in before
    assert sorted(after) == sorted([*before, "Alien mug"])


async def test_other_peoples_subtypes_are_not_followed() -> None:
    """A parent slug only reaches the caller's own subtypes."""
    repos = await _world()
    other = uuid.UUID(int=2)
    await repos.node_types.add(
        NodeType.create(
            owner_id=other,
            slug="mug",
            label="Mug",
            attributes_schema=_schema(),
            parent="memorabilia",
        )
    )
    await repos.nodes.add(Node.create(owner_id=other, name="Theirs", type="mug"))

    found = await _names(repos, _query(_type("memorabilia")))

    assert "Theirs" not in found
