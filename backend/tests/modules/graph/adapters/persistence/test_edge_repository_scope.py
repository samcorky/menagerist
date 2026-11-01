"""Every scoped `EdgeRepository` method, against the in-memory and Postgres adapters."""

import uuid
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest

from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.edge_repository import EdgeRepository
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = ContentFilter.of(ALICE)
B = ContentFilter.of(BOB)
ALL = ContentFilter.everyone()


class _Repos(NamedTuple):
    edges: EdgeRepository
    nodes: NodeRepository


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repos(request: pytest.FixtureRequest) -> _Repos:
    """The same scenarios run against both adapters."""
    if request.param == "in_memory":
        return _Repos(InMemoryEdgeRepository(), InMemoryNodeRepository())
    session = request.getfixturevalue("db_session")
    return _Repos(SqlAlchemyEdgeRepository(session), SqlAlchemyNodeRepository(session))


async def _edge(
    repos: _Repos,
    owner: uuid.UUID | None,
    *,
    type: str = "related-to",
    source: Node | None = None,
    target: Node | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> Edge:
    """Persist an edge (and endpoints when not given) owned by `owner`."""
    nodes = []
    for end in (source, target):
        if end is None:
            end = Node.create(owner_id=ALICE, name="Item")
            await repos.nodes.add(end)
        nodes.append(end)
    edge = Edge.create(
        owner_id=ALICE,
        source_id=nodes[0].id,
        target_id=nodes[1].id,
        type=type,
        **kwargs,
    )
    edge.owner_id = owner
    await repos.edges.add(edge)
    return edge


async def _ids(repos: _Repos, scope: ContentFilter, **kwargs: Any) -> list[uuid.UUID]:  # noqa: ANN401
    page = await repos.edges.list(scope=scope, after=None, limit=50, **kwargs)
    return [e.id for e in page]


async def test_get_hides_other_users_edges(repos: _Repos) -> None:
    """A's edge is visible to A and everyone(), never to B."""
    edge = await _edge(repos, ALICE)

    assert await repos.edges.get(edge.id, scope=A) is not None
    assert await repos.edges.get(edge.id, scope=ALL) is not None
    assert await repos.edges.get(edge.id, scope=B) is None


async def test_owner_round_trips(repos: _Repos) -> None:
    """The owner survives a save and a read."""
    edge = await _edge(repos, ALICE)

    fetched = await repos.edges.get(edge.id, scope=ALL)

    assert fetched is not None
    assert fetched.owner_id == ALICE


async def test_get_hides_soft_deleted_edges(repos: _Repos) -> None:
    """A soft-deleted edge is invisible even to its owner and everyone()."""
    edge = await _edge(repos, ALICE)
    edge.soft_delete()
    await repos.edges.save(edge)

    assert await repos.edges.get(edge.id, scope=A) is None
    assert await repos.edges.get(edge.id, scope=ALL) is None


async def test_ownerless_edges_are_visible_only_to_everyone(repos: _Repos) -> None:
    """A NULL-owner row belongs to nobody: only the all-scope sees it."""
    orphan = await _edge(repos, None, attributes={"k": "v"})

    assert await repos.edges.get(orphan.id, scope=A) is None
    assert await repos.edges.get(orphan.id, scope=ALL) is not None
    assert await _ids(repos, A) == []
    assert await _ids(repos, ALL) == [orphan.id]
    assert (
        await repos.edges.list_for_node(orphan.source_id, scope=A, after=None, limit=10)
        == []
    )
    assert await repos.edges.has_edges_of_type("related-to", scope=A) is False
    assert await repos.edges.has_edges_of_type("related-to", scope=ALL) is True
    assert await repos.edges.count_with_attribute("related-to", "k", scope=A) == 0
    assert await repos.edges.count_with_attribute("related-to", "k", scope=ALL) == 1
    assert (
        await repos.edges.list_with_attribute(
            "related-to", "k", scope=A, after=None, limit=10
        )
        == []
    )


async def test_list_is_scoped_and_paginates_inside_the_scope(repos: _Repos) -> None:
    """Each user lists only their own edges, and paging never crosses owners."""
    mine = [await _edge(repos, ALICE) for _ in range(3)]
    theirs = [await _edge(repos, BOB) for _ in range(2)]
    gone = await _edge(repos, ALICE)
    gone.soft_delete()
    await repos.edges.save(gone)

    assert set(await _ids(repos, A)) == {e.id for e in mine}
    assert set(await _ids(repos, B)) == {e.id for e in theirs}
    assert set(await _ids(repos, ALL)) == {e.id for e in [*mine, *theirs]}

    first = await repos.edges.list(scope=A, after=None, limit=2)
    rest = await repos.edges.list(scope=A, after=first[-1].id, limit=2)
    assert [e.id for e in [*first, *rest]] == sorted(e.id for e in mine)


async def test_list_for_node_is_scoped(repos: _Repos) -> None:
    """A node's connections are filtered by owner, in both directions."""
    hub = Node.create(owner_id=ALICE, name="Hub")
    await repos.nodes.add(hub)
    out = await _edge(repos, ALICE, source=hub)
    inbound = await _edge(repos, ALICE, target=hub)
    foreign = await _edge(repos, BOB, source=hub)
    gone = await _edge(repos, ALICE, source=hub)
    gone.soft_delete()
    await repos.edges.save(gone)

    mine = await repos.edges.list_for_node(hub.id, scope=A, after=None, limit=50)
    theirs = await repos.edges.list_for_node(hub.id, scope=B, after=None, limit=50)
    everyone = await repos.edges.list_for_node(hub.id, scope=ALL, after=None, limit=50)

    assert {e.id for e in mine} == {out.id, inbound.id}
    assert {e.id for e in theirs} == {foreign.id}
    assert {e.id for e in everyone} == {out.id, inbound.id, foreign.id}
    page = await repos.edges.list_for_node(hub.id, scope=A, after=None, limit=1)
    after = await repos.edges.list_for_node(hub.id, scope=A, after=page[0].id, limit=50)
    assert len(page) + len(after) == 2


async def test_has_edges_of_type_is_scoped(repos: _Repos) -> None:
    """Only the viewer's live edges of the type count as usage."""
    await _edge(repos, ALICE, type="owns")
    gone = await _edge(repos, BOB, type="likes")
    gone.soft_delete()
    await repos.edges.save(gone)

    assert await repos.edges.has_edges_of_type("owns", scope=A) is True
    assert await repos.edges.has_edges_of_type("owns", scope=B) is False
    assert await repos.edges.has_edges_of_type("owns", scope=ALL) is True
    assert await repos.edges.has_edges_of_type("likes", scope=B) is False
    assert await repos.edges.has_edges_of_type("likes", scope=ALL) is False


async def test_count_and_list_with_attribute_match_and_are_scoped(
    repos: _Repos,
) -> None:
    """Counts equal list totals for the same scope, plain keys and group sub-keys."""
    a1 = await _edge(repos, ALICE, type="owns", attributes={"note": "x"})
    a2 = await _edge(repos, ALICE, type="owns", attributes={"note": "y"})
    b1 = await _edge(repos, BOB, type="owns", attributes={"note": "x"})
    a_group = await _edge(
        repos, ALICE, type="owns", attributes={"rows": [{"qty": "2"}]}
    )
    b_group = await _edge(repos, BOB, type="owns", attributes={"rows": [{"qty": "2"}]})
    gone = await _edge(repos, ALICE, type="owns", attributes={"note": "z"})
    gone.soft_delete()
    await repos.edges.save(gone)

    async def listed(
        scope: ContentFilter, key: str, sub_key: str | None = None
    ) -> set[uuid.UUID]:
        page = await repos.edges.list_with_attribute(
            "owns", key, scope=scope, sub_key=sub_key, after=None, limit=50
        )
        return {e.id for e in page}

    for scope, expected_notes, expected_groups in (
        (A, {a1.id, a2.id}, {a_group.id}),
        (B, {b1.id}, {b_group.id}),
        (ALL, {a1.id, a2.id, b1.id}, {a_group.id, b_group.id}),
    ):
        assert await listed(scope, "note") == expected_notes
        assert await repos.edges.count_with_attribute(
            "owns", "note", scope=scope
        ) == len(expected_notes)
        assert await listed(scope, "rows", "qty") == expected_groups
        assert await repos.edges.count_with_attribute(
            "owns", "rows", scope=scope, sub_key="qty"
        ) == len(expected_groups)

    assert (
        await repos.edges.count_with_attribute("owns", "note", scope=A, value="x") == 1
    )
    assert (
        await repos.edges.count_with_attribute("owns", "note", scope=B, value="y") == 0
    )
    paged = await repos.edges.list_with_attribute(
        "owns", "note", scope=A, after=None, limit=1
    )
    rest = await repos.edges.list_with_attribute(
        "owns", "note", scope=A, after=paged[0].id, limit=50
    )
    assert len(paged) + len(rest) == 2
