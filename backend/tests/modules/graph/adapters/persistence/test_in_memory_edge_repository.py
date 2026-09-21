import uuid

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.domain.edge import Edge


def _make_edge() -> Edge:
    return Edge.create(
        source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="related-to"
    )


async def test_add_and_get_round_trips() -> None:
    """An edge added to the repository can be retrieved by id."""
    repository = InMemoryEdgeRepository()
    edge = _make_edge()

    await repository.add(edge)

    assert await repository.get(edge.id) is edge


async def test_get_returns_none_for_missing_edge() -> None:
    """get() returns None for an id that was never added."""
    repository = InMemoryEdgeRepository()

    assert await repository.get(uuid.uuid4()) is None


async def test_get_returns_none_for_a_soft_deleted_edge() -> None:
    """get() treats a soft-deleted edge as if it doesn't exist."""
    repository = InMemoryEdgeRepository()
    edge = _make_edge()
    await repository.add(edge)

    edge.soft_delete()
    await repository.save(edge)

    assert await repository.get(edge.id) is None


async def test_save_persists_changes_to_an_existing_edge() -> None:
    """save() overwrites the stored edge with the given instance."""
    repository = InMemoryEdgeRepository()
    edge = _make_edge()
    await repository.add(edge)

    edge.attributes = {"since": "1979"}
    await repository.save(edge)

    result = await repository.get(edge.id)
    assert result is not None
    assert result.attributes == {"since": "1979"}


async def test_list_orders_by_id_ascending() -> None:
    """list() returns edge ordered by id ascending, regardless of insert order."""
    repository = InMemoryEdgeRepository()
    edges = [_make_edge() for _ in range(3)]
    for edge in reversed(edges):
        await repository.add(edge)

    result = await repository.list(after=None, limit=10)

    assert result == sorted(edges, key=lambda edge: edge.id)


async def test_list_excludes_soft_deleted_edges() -> None:
    """list() omits soft-deleted edge."""
    repository = InMemoryEdgeRepository()
    kept = _make_edge()
    deleted = _make_edge()
    await repository.add(kept)
    await repository.add(deleted)

    deleted.soft_delete()
    await repository.save(deleted)

    result = await repository.list(after=None, limit=10)

    assert result == [kept]


async def test_list_for_node_returns_edges_touching_the_node_either_direction() -> None:
    """list_for_node() returns edge where the node is either source or target."""
    repository = InMemoryEdgeRepository()
    node_id = uuid.uuid4()
    outgoing = Edge.create(source_id=node_id, target_id=uuid.uuid4(), type="owns")
    incoming = Edge.create(source_id=uuid.uuid4(), target_id=node_id, type="owned-by")
    unrelated = _make_edge()
    for edge in (outgoing, incoming, unrelated):
        await repository.add(edge)

    result = await repository.list_for_node(node_id, after=None, limit=10)

    assert set(result) == {outgoing, incoming}


async def test_list_for_node_respects_after_and_limit() -> None:
    """list_for_node() paginates using after/limit."""
    repository = InMemoryEdgeRepository()
    node_id = uuid.uuid4()
    edges = sorted(
        (
            Edge.create(source_id=node_id, target_id=uuid.uuid4(), type="owns")
            for _ in range(4)
        ),
        key=lambda edge: edge.id,
    )
    for edge in edges:
        await repository.add(edge)

    page = await repository.list_for_node(node_id, after=edges[0].id, limit=2)

    assert page == edges[1:3]


async def test_has_edges_of_type_returns_true_when_matching_edge_exists() -> None:
    """has_edges_of_type() returns True when a non-deleted edge uses that type."""
    repository = InMemoryEdgeRepository()
    edge = Edge.create(
        source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="directed-by"
    )
    await repository.add(edge)

    assert await repository.has_edges_of_type("directed-by") is True


async def test_has_edges_of_type_returns_false_when_no_match() -> None:
    """has_edges_of_type() returns False when no edges use that type."""
    repository = InMemoryEdgeRepository()
    edge = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    await repository.add(edge)

    assert await repository.has_edges_of_type("directed-by") is False


async def test_has_edges_of_type_ignores_soft_deleted_edges() -> None:
    """has_edges_of_type() does not count soft-deleted edges."""
    repository = InMemoryEdgeRepository()
    edge = Edge.create(
        source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="directed-by"
    )
    await repository.add(edge)
    edge.soft_delete()
    await repository.save(edge)

    assert await repository.has_edges_of_type("directed-by") is False


async def test_count_and_list_with_attribute_filter_by_type_key_and_deletion() -> None:
    """Only live edges of the type holding the key are counted and listed, by id."""
    repository = InMemoryEdgeRepository()
    source, target = uuid.uuid4(), uuid.uuid4()

    def make(type_: str, attributes: dict[str, int]) -> Edge:
        return Edge.create(
            source_id=source, target_id=target, type=type_, attributes=attributes
        )

    edges = [make("owns", {"k": i}) for i in range(3)]
    gone = make("owns", {"k": 9})
    gone.soft_delete()
    for edge in [*edges, make("likes", {"k": 1}), make("owns", {}), gone]:
        await repository.add(edge)

    assert await repository.count_with_attribute("owns", "k") == 3
    page = await repository.list_with_attribute("owns", "k", after=None, limit=2)
    assert [e.id for e in page] == sorted(e.id for e in edges)[:2]
    rest = await repository.list_with_attribute(
        "owns", "k", after=page[-1].id, limit=10
    )
    assert [e.id for e in rest] == sorted(e.id for e in edges)[2:]


async def test_count_with_attribute_can_match_a_value() -> None:
    """With `value`, only edges whose attribute equals it are counted."""
    repository = InMemoryEdgeRepository()
    source, target = uuid.uuid4(), uuid.uuid4()
    for status in ["Draft", "Draft", "Live"]:
        await repository.add(
            Edge.create(
                source_id=source,
                target_id=target,
                type="owns",
                attributes={"s": status},
            )
        )

    assert await repository.count_with_attribute("owns", "s", value="Draft") == 2
    assert await repository.count_with_attribute("owns", "s", value="Gone") == 0
