"""Listing the subtypes of a parent type."""

import uuid

import pytest

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.list_subtypes import ListSubtypes, ListSubtypesQuery
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _add(repos: GraphRepos, slug: str, parent: str | None = None) -> NodeType:
    node_type = NodeType.create(
        owner_id=SYSTEM_ACTOR.id, slug=slug, label=slug.title(), parent=parent
    )
    await repos.node_types.add(node_type)
    return node_type


async def test_lists_the_subtypes_of_the_parent_by_id() -> None:
    """Only that parent's subtypes, in id order."""
    repos = _repos()
    memorabilia = await _add(repos, "memorabilia")
    await _add(repos, "poster", "memorabilia")
    await _add(repos, "figure", "memorabilia")
    await _add(repos, "vinyl", "music-media")

    found = await ListSubtypes(repos, InMemoryAccessGuard()).handle(
        ListSubtypesQuery(node_type_id=memorabilia.id), SYSTEM_ACTOR
    )

    assert [str(t.slug) for t in found] == ["poster", "figure"]


async def test_pages_with_after_and_limit() -> None:
    """The keyset cursor and limit work as on the other lists."""
    repos = _repos()
    memorabilia = await _add(repos, "memorabilia")
    poster = await _add(repos, "poster", "memorabilia")
    await _add(repos, "figure", "memorabilia")
    await _add(repos, "mug", "memorabilia")
    use_case = ListSubtypes(repos, InMemoryAccessGuard())

    first = await use_case.handle(
        ListSubtypesQuery(node_type_id=memorabilia.id, limit=2), SYSTEM_ACTOR
    )
    rest = await use_case.handle(
        ListSubtypesQuery(node_type_id=memorabilia.id, after=poster.id), SYSTEM_ACTOR
    )

    assert [str(t.slug) for t in first] == ["poster", "figure"]
    assert [str(t.slug) for t in rest] == ["figure", "mug"]


async def test_a_type_with_no_subtypes_lists_none() -> None:
    """A top-level type that nothing is under has an empty list."""
    repos = _repos()
    book = await _add(repos, "book")

    found = await ListSubtypes(repos, InMemoryAccessGuard()).handle(
        ListSubtypesQuery(node_type_id=book.id), SYSTEM_ACTOR
    )

    assert found == []


async def test_an_unknown_type_is_not_found() -> None:
    """The parent has to exist."""
    with pytest.raises(NodeTypeNotFoundError):
        await ListSubtypes(_repos(), InMemoryAccessGuard()).handle(
            ListSubtypesQuery(node_type_id=uuid.uuid4()), SYSTEM_ACTOR
        )
