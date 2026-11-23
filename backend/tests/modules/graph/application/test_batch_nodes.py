"""DeleteNodes and TagNodes: several items in one transaction, all or none."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
    create_in_memory_graph_uow,
)
from app.modules.graph.application.delete_nodes import DeleteNodes, DeleteNodesCommand
from app.modules.graph.application.tag_nodes import TagNodes, TagNodesCommand
from app.modules.graph.domain.node import Node
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphRepos

OWNER = uuid.UUID(int=1)


async def _nodes(repos: GraphRepos, *tags: list[str]) -> list[Node]:
    made = [
        Node.create(owner_id=OWNER, name=f"Item {i}", type="film", tags=list(t))
        for i, t in enumerate(tags)
    ]
    for node in made:
        await repos.nodes.add(node)
    return made


async def _tags(repos: GraphRepos, node: Node) -> list[str]:
    stored = await repos.nodes.get(node.id, scope=ContentFilter.everyone())
    assert stored is not None
    return stored.tags


async def _alive(repos: GraphRepos, node: Node) -> bool:
    return await repos.nodes.get(node.id, scope=ContentFilter.everyone()) is not None


def _delete(repos: GraphRepos) -> DeleteNodes:
    return DeleteNodes(create_in_memory_graph_uow(repos), InMemoryAccessGuard())


def _tag(repos: GraphRepos) -> TagNodes:
    return TagNodes(create_in_memory_graph_uow(repos), InMemoryAccessGuard())


async def test_delete_nodes_deletes_every_item() -> None:
    """Delete nodes deletes every item."""
    repos = build_in_memory_graph_repos()
    nodes = await _nodes(repos, [], [], [])

    await _delete(repos).handle(
        DeleteNodesCommand(node_ids=[n.id for n in nodes]), SYSTEM_ACTOR
    )

    assert [await _alive(repos, n) for n in nodes] == [False, False, False]


async def test_delete_nodes_changes_nothing_when_one_id_is_unknown() -> None:
    """Delete nodes changes nothing when one id is unknown."""
    repos = build_in_memory_graph_repos()
    nodes = await _nodes(repos, [], [])
    ghost = uuid.uuid4()

    with pytest.raises(ValidationError, match=f"Unknown or deleted items: {ghost}"):
        await _delete(repos).handle(
            DeleteNodesCommand(node_ids=[nodes[0].id, ghost, nodes[1].id]),
            SYSTEM_ACTOR,
        )

    assert [await _alive(repos, n) for n in nodes] == [True, True]


async def test_delete_nodes_collapses_duplicate_ids() -> None:
    """Delete nodes collapses duplicate ids."""
    repos = build_in_memory_graph_repos()
    (node,) = await _nodes(repos, [])

    await _delete(repos).handle(
        DeleteNodesCommand(node_ids=[node.id, node.id]), SYSTEM_ACTOR
    )

    assert not await _alive(repos, node)


@pytest.mark.parametrize("count", [0, 201])
async def test_delete_nodes_refuses_an_empty_or_oversized_batch(count: int) -> None:
    """Delete nodes refuses an empty or oversized batch."""
    repos = build_in_memory_graph_repos()

    with pytest.raises(ValidationError):
        await _delete(repos).handle(
            DeleteNodesCommand(node_ids=[uuid.uuid4() for _ in range(count)]),
            SYSTEM_ACTOR,
        )


async def test_tag_nodes_adds_and_removes_tags() -> None:
    """Tag nodes adds and removes tags."""
    repos = build_in_memory_graph_repos()
    a, b, c = await _nodes(repos, ["old"], ["old", "keep"], [])

    updated = await _tag(repos).handle(
        TagNodesCommand(
            node_ids=[a.id, b.id, c.id], add=[" New ", "keep"], remove=["old"]
        ),
        SYSTEM_ACTOR,
    )

    assert updated == 3
    assert await _tags(repos, a) == ["new", "keep"]
    assert await _tags(repos, b) == ["keep", "new"]
    assert await _tags(repos, c) == ["new", "keep"]


async def test_tag_nodes_does_not_count_items_that_already_match() -> None:
    """Tag nodes does not count items that already match."""
    repos = build_in_memory_graph_repos()
    a, b = await _nodes(repos, ["x"], [])

    updated = await _tag(repos).handle(
        TagNodesCommand(node_ids=[a.id, b.id], add=["x"]), SYSTEM_ACTOR
    )

    assert updated == 1
    assert await _tags(repos, a) == ["x"]


async def test_tag_nodes_needs_a_tag_to_add_or_remove() -> None:
    """Tag nodes needs a tag to add or remove."""
    repos = build_in_memory_graph_repos()
    (a,) = await _nodes(repos, [])

    with pytest.raises(ValidationError):
        await _tag(repos).handle(
            TagNodesCommand(node_ids=[a.id], add=["  "], remove=[]), SYSTEM_ACTOR
        )


async def test_tag_nodes_changes_nothing_when_one_id_is_unknown() -> None:
    """Tag nodes changes nothing when one id is unknown."""
    repos = build_in_memory_graph_repos()
    (a,) = await _nodes(repos, [])

    with pytest.raises(ValidationError, match="Unknown or deleted items"):
        await _tag(repos).handle(
            TagNodesCommand(node_ids=[a.id, uuid.uuid4()], add=["x"]), SYSTEM_ACTOR
        )

    assert await _tags(repos, a) == []
