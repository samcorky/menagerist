"""Tests for finding nodes by name or attribute value (in-memory)."""

import uuid

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.shared_kernel.content_filter import ContentFilter

OWNER = uuid.UUID(int=1)
OTHER = uuid.UUID(int=2)


def _node(
    name: str = "n",
    *,
    type_: str | None = "film",
    attributes: dict[str, object] | None = None,
    owner: uuid.UUID = OWNER,
) -> Node:
    return Node.create(
        owner_id=owner, name=name, type=type_, attributes=attributes or {}
    )


async def _repo(*nodes: Node) -> InMemoryNodeRepository:
    repository = InMemoryNodeRepository()
    for node in nodes:
        await repository.add(node)
    return repository


async def test_ids_with_attribute_value_finds_exact_string_matches() -> None:
    """Ids with attribute value finds exact string matches."""
    a = _node(attributes={"upc": "0123"})
    repo = await _repo(a, _node(attributes={"upc": "9999"}), _node())
    found = await repo.ids_with_attribute_value(
        "film", "upc", "0123", scope=ContentFilter.of(OWNER), limit=5
    )
    assert found == [a.id]


async def test_ids_with_attribute_value_ignores_lists_and_other_types() -> None:
    """Ids with attribute value ignores lists and other types."""
    repo = await _repo(
        _node(attributes={"tags": ["0123"]}),
        _node(type_="book", attributes={"upc": "0123"}),
        _node(type_=None, attributes={"upc": "0123"}),
    )
    scope = ContentFilter.of(OWNER)
    assert (
        await repo.ids_with_attribute_value(
            "film", "tags", "0123", scope=scope, limit=5
        )
        == []
    )
    assert (
        await repo.ids_with_attribute_value("film", "upc", "0123", scope=scope, limit=5)
        == []
    )


async def test_ids_with_attribute_value_orders_by_id_and_limits() -> None:
    """Ids with attribute value orders by id and limits."""
    nodes = [_node(attributes={"upc": "1"}) for _ in range(3)]
    repo = await _repo(*nodes)
    found = await repo.ids_with_attribute_value(
        "film", "upc", "1", scope=ContentFilter.of(OWNER), limit=2
    )
    assert found == sorted(n.id for n in nodes)[:2]


async def test_ids_with_attribute_value_skips_deleted_and_other_owners() -> None:
    """Ids with attribute value skips deleted and other owners."""
    gone = _node(attributes={"upc": "1"})
    gone.soft_delete()
    repo = await _repo(gone, _node(attributes={"upc": "1"}, owner=OTHER))
    found = await repo.ids_with_attribute_value(
        "film", "upc", "1", scope=ContentFilter.of(OWNER), limit=5
    )
    assert found == []


async def test_ids_with_name_matches_exactly_within_the_type() -> None:
    """Ids with name matches exactly within the type."""
    alien = _node("Alien")
    repo = await _repo(
        alien, _node("alien"), _node("Alien", type_="book"), _node("Aliens")
    )
    found = await repo.ids_with_name(
        "film", "Alien", scope=ContentFilter.of(OWNER), limit=5
    )
    assert found == [alien.id]


async def test_ids_with_name_skips_deleted_and_other_owners() -> None:
    """Ids with name skips deleted and other owners."""
    gone = _node("Alien")
    gone.soft_delete()
    repo = await _repo(gone, _node("Alien", owner=OTHER))
    found = await repo.ids_with_name(
        "film", "Alien", scope=ContentFilter.of(OWNER), limit=5
    )
    assert found == []
