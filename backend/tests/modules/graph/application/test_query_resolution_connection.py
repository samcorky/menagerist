import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.graph.adapters.persistence.in_memory_external_conditions import (
    InMemoryExternalConditions,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
)
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import (
    InvalidQueryError,
    QueryWarning,
    RelationshipInfo,
)
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphRepos

ALICE = uuid.UUID(int=1)
BOB = uuid.UUID(int=2)
TODAY = date(2026, 10, 24)
SCOPE = ContentFilter.of(ALICE)
_C = "where.children[0]"


def _query(*children: dict[str, Any]) -> dict[str, Any]:
    return {"v": 1, "where": {"op": "and", "children": list(children)}}


def _conn(mode: str = "exists", **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"kind": "connection", "mode": mode, **extra}


class _Counting:
    """Counts reads of the lookups connection resolution should batch."""

    def __init__(self, repos: GraphRepos) -> None:
        self.edge_type_reads = 0
        self.node_reads = 0
        edge_types_list = repos.edge_types.list
        nodes_list = repos.nodes.list

        async def edge_types(**kwargs: Any) -> Any:  # noqa: ANN401
            self.edge_type_reads += 1
            return await edge_types_list(**kwargs)

        async def nodes(**kwargs: Any) -> Any:  # noqa: ANN401
            self.node_reads += 1
            return await nodes_list(**kwargs)

        repos.edge_types.list = edge_types  # type: ignore[method-assign]
        repos.nodes.list = nodes  # type: ignore[method-assign]


@pytest.fixture
def external() -> InMemoryExternalConditions:
    """The external source shared by the repositories and the definitions."""
    return InMemoryExternalConditions()


@pytest.fixture
async def repos(external: InMemoryExternalConditions) -> GraphRepos:
    """In-memory repositories with two item types and live and deleted relationships."""
    built = build_in_memory_graph_repos(external=external, definitions=external)
    await built.node_types.add(
        NodeType.create(
            slug="film",
            label="Film",
            attributes_schema={
                "type": "object",
                "properties": {"year": {"type": "number"}},
            },
        )
    )
    await built.edge_types.add(EdgeType.create(slug="made-by", label="Made by"))
    await built.edge_types.add(
        EdgeType.create(slug="related", label="Related", directional=False)
    )
    gone = EdgeType.create(slug="retired", label="Retired")
    gone.soft_delete()
    await built.edge_types.add(gone)
    return built


async def _item(repos: GraphRepos, owner: uuid.UUID, *, deleted: bool = False) -> Node:
    node = Node.create(owner_id=owner, name="x", type="film")
    if deleted:
        node.soft_delete()
    await repos.nodes.add(node)
    return node


async def test_known_relationships_resolve_with_their_direction(
    repos: GraphRepos,
) -> None:
    """Each named slug maps to its directional flag."""
    resolved, warnings = await prepare_query(
        repos,
        _query(
            _conn(relationship="made-by"),
            _conn("none", relationship="related"),
            _conn(relationship="made-by", direction="in"),
        ),
        TODAY,
        scope=SCOPE,
    )
    assert resolved.relationships == {
        "made-by": RelationshipInfo(slug="made-by", directional=True),
        "related": RelationshipInfo(slug="related", directional=False),
    }
    assert resolved.visible_items == frozenset()
    assert warnings == []


@pytest.mark.parametrize("slug", ["unknown", "retired"])
async def test_an_unknown_or_deleted_relationship_warns(
    repos: GraphRepos, slug: str
) -> None:
    """The condition stays, is left out of `relationships` and warns with its path."""
    resolved, warnings = await prepare_query(
        repos, _query(_conn(relationship=slug)), TODAY, scope=SCOPE
    )
    assert resolved.relationships == {}
    assert [w.path for w in warnings] == [_C]
    assert slug in warnings[0].message


async def test_a_connection_without_a_relationship_needs_no_lookup(
    repos: GraphRepos,
) -> None:
    """No slug and no item means no reads and no warnings."""
    counting = _Counting(repos)
    resolved, warnings = await prepare_query(repos, _query(_conn()), TODAY, scope=SCOPE)
    assert (counting.edge_type_reads, counting.node_reads) == (0, 0)
    assert resolved.relationships == {}
    assert warnings == []


async def test_a_visible_target_item_resolves(repos: GraphRepos) -> None:
    """A live item in scope is listed as visible."""
    item = await _item(repos, ALICE)
    resolved, warnings = await prepare_query(
        repos, _query(_conn("to", item=str(item.id))), TODAY, scope=SCOPE
    )
    assert resolved.visible_items == frozenset({item.id})
    assert warnings == []


async def test_deleted_foreign_and_unknown_target_items_warn(
    repos: GraphRepos,
) -> None:
    """A deleted, another owner's or unknown item is stale, all reading alike."""
    deleted = await _item(repos, ALICE, deleted=True)
    foreign = await _item(repos, BOB)
    unknown = uuid.UUID(int=99)
    live = await _item(repos, ALICE)
    resolved, warnings = await prepare_query(
        repos,
        _query(
            _conn("to", item=str(deleted.id)),
            _conn("to", item=str(foreign.id)),
            _conn("to", item=str(unknown)),
            _conn("to", item=str(live.id)),
        ),
        TODAY,
        scope=SCOPE,
    )
    assert resolved.visible_items == frozenset({live.id})
    assert [w.path for w in warnings] == [
        "where.children[0]",
        "where.children[1]",
        "where.children[2]",
    ]
    assert len({w.message for w in warnings}) == 1


async def test_lookups_are_batched(repos: GraphRepos) -> None:
    """Many conditions cost one edge-type read and one item read."""
    items = [await _item(repos, ALICE) for _ in range(3)]
    counting = _Counting(repos)
    await prepare_query(
        repos,
        _query(
            *(_conn("to", relationship="made-by", item=str(i.id)) for i in items),
            _conn(relationship="related"),
            _conn(relationship="unknown"),
        ),
        TODAY,
        scope=SCOPE,
    )
    assert counting.edge_type_reads == 1
    assert counting.node_reads == 1


async def test_far_end_fields_resolve_and_go_stale_with_a_nested_path(
    repos: GraphRepos,
) -> None:
    """A removed field in `where` warns under it and is stale; a live one has a kind."""
    live = {"kind": "field", "type": "film", "key": "year", "op": ">", "value": 1}
    gone = {"kind": "field", "type": "film", "key": "gone", "op": "=", "value": 1}
    resolved, warnings = await prepare_query(
        repos,
        _query(_conn(where={"op": "or", "children": [live, gone]})),
        TODAY,
        scope=SCOPE,
    )
    assert resolved.field_kinds == {("film", "year", None): "number"}
    assert [w.path for w in warnings] == [f"{_C}.where.children[1]"]
    assert len(resolved.stale) == 1


async def test_a_wrong_operator_in_the_far_end_is_a_400(repos: GraphRepos) -> None:
    """Only gone fields warn; a bad operator for a live field is refused."""
    bad = {"kind": "field", "type": "film", "key": "year", "op": "~", "value": "x"}
    with pytest.raises(InvalidQueryError) as caught:
        await prepare_query(
            repos,
            _query(_conn(where={"op": "and", "children": [bad]})),
            TODAY,
            scope=SCOPE,
        )
    assert caught.value.path == f"{_C}.where.children[0]"


async def test_connections_inside_a_smart_collection_resolve(
    repos: GraphRepos, external: InMemoryExternalConditions
) -> None:
    """An inlined smart collection's connections are resolved with nested paths."""
    smart_id = uuid.UUID(int=500)
    item = await _item(repos, ALICE)
    external.add_collection(
        smart_id,
        owner_id=ALICE,
        definition=_query(
            _conn(relationship="made-by"),
            _conn("to", relationship="nope", item=str(item.id)),
        ),
    )
    resolved, warnings = await prepare_query(
        repos,
        _query({"kind": "collection", "mode": "any", "in": [str(smart_id)]}),
        TODAY,
        scope=SCOPE,
    )
    assert set(resolved.relationships) == {"made-by"}
    assert resolved.visible_items == frozenset({item.id})
    assert warnings == [
        QueryWarning(
            f"{_C}.in[0].children[1]", "The relationship 'nope' no longer exists."
        )
    ]


async def test_collections_inside_a_far_end_filter_are_expanded(
    repos: GraphRepos, external: InMemoryExternalConditions
) -> None:
    """A collection condition in `where` gets its targets, with a nested path."""
    unknown = uuid.UUID(int=77)
    _, warnings = await prepare_query(
        repos,
        _query(
            _conn(
                where={
                    "op": "and",
                    "children": [
                        {"kind": "collection", "mode": "any", "in": [str(unknown)]}
                    ],
                }
            )
        ),
        TODAY,
        scope=SCOPE,
    )
    assert [w.path for w in warnings] == [f"{_C}.where.children[0].in[0]"]


async def test_without_an_external_source_far_end_media_warns(
    repos: GraphRepos,
) -> None:
    """The cannot-check warning also covers conditions in the far-end filter."""
    repos.external = None
    _, warnings = await prepare_query(
        repos,
        _query(
            _conn(where={"op": "and", "children": [{"kind": "media", "mode": "has"}]})
        ),
        TODAY,
        scope=SCOPE,
    )
    assert [w.path for w in warnings] == [f"{_C}.where.children[0]"]
