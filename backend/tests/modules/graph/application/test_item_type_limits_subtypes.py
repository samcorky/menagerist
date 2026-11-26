"""A connection type's limit on a parent item type covers its subtypes (#771)."""

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
from app.modules.graph.application.create_edge import CreateEdge, CreateEdgeCommand
from app.modules.graph.application.create_edges import CreateEdges, CreateEdgesCommand
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import ItemTypeNotAllowedError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

ME = SYSTEM_ACTOR.id


async def _world(
    *, target_types: tuple[str, ...] = (), source_types: tuple[str, ...] = ()
) -> tuple[GraphRepos, dict[str, Node]]:
    """Memorabilia with Poster and Figure beneath it, a stand-alone Box, items of each.

    The connection type "stored-in" carries the limits given.
    """
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    for slug, parent in (
        ("memorabilia", None),
        ("poster", "memorabilia"),
        ("figure", "memorabilia"),
        ("box", None),
    ):
        await repos.node_types.add(
            NodeType.create(owner_id=ME, slug=slug, label=slug.title(), parent=parent)
        )
    items = {
        slug: Node.create(owner_id=ME, name=f"A {slug}", type=slug)
        for slug in ("memorabilia", "poster", "figure", "box")
    }
    for item in items.values():
        await repos.nodes.add(item)
    await repos.edge_types.add(
        EdgeType.create(
            owner_id=ME,
            slug="stored-in",
            label="Stored in",
            source_types=source_types,
            target_types=target_types,
        )
    )
    return repos, items


async def _connect(repos: GraphRepos, source: Node, target: Node) -> None:
    await CreateEdge(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgeCommand(source_id=source.id, target_id=target.id, type="stored-in"),
        SYSTEM_ACTOR,
    )


async def test_a_limit_on_a_parent_accepts_its_subtypes_and_itself() -> None:
    """Stored in, limited to Memorabilia, takes a poster, a figure and memorabilia."""
    repos, items = await _world(target_types=("memorabilia",))

    for slug in ("poster", "figure", "memorabilia"):
        await _connect(repos, items["box"], items[slug])


async def test_a_limit_on_a_parent_still_refuses_other_types() -> None:
    """A type outside the family is not covered."""
    repos, items = await _world(target_types=("memorabilia",))

    with pytest.raises(ItemTypeNotAllowedError, match="A box"):
        await _connect(repos, items["poster"], items["box"])


async def test_a_limit_on_a_subtype_covers_only_that_subtype() -> None:
    """Neither its parent nor its sibling is allowed."""
    repos, items = await _world(target_types=("poster",))

    await _connect(repos, items["box"], items["poster"])
    for slug in ("memorabilia", "figure"):
        with pytest.raises(ItemTypeNotAllowedError):
            await _connect(repos, items["box"], items[slug])


async def test_the_source_end_follows_subtypes_too() -> None:
    """The rule holds at either end."""
    repos, items = await _world(source_types=("memorabilia",))

    await _connect(repos, items["figure"], items["box"])
    with pytest.raises(ItemTypeNotAllowedError, match="at its source"):
        await _connect(repos, items["box"], items["figure"])


async def test_a_batch_accepts_subtypes_and_refuses_the_whole_batch_for_one_stray() -> (
    None
):
    """CreateEdges checks every target with the same rule, writing nothing on a miss."""
    repos, items = await _world(target_types=("memorabilia",))
    stranger = Node.create(owner_id=uuid.UUID(int=ME.int), name="Stray", type="box")
    await repos.nodes.add(stranger)

    created = await CreateEdges(
        InMemoryUnitOfWork(repos), InMemoryAccessGuard()
    ).handle(
        CreateEdgesCommand(
            source_id=items["box"].id,
            target_ids=[items["poster"].id, items["figure"].id],
            type="stored-in",
        ),
        SYSTEM_ACTOR,
    )
    assert len(created.created) == 2

    uow = InMemoryUnitOfWork(repos)
    with pytest.raises(ItemTypeNotAllowedError, match="Stray"):
        await CreateEdges(uow, InMemoryAccessGuard()).handle(
            CreateEdgesCommand(
                source_id=items["box"].id,
                target_ids=[items["memorabilia"].id, stranger.id],
                type="stored-in",
            ),
            SYSTEM_ACTOR,
        )
    assert uow.committed is False
