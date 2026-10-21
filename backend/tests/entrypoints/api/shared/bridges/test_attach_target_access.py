"""The media-to-graph bridge: which items and connections a person may attach to."""

import uuid

import pytest

from app.entrypoints.api.shared.bridges.attach_target_access import (
    GraphAttachTargetAccess,
)
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
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.shared_kernel.content_filter import ContentFilter

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = ContentFilter.of(ALICE)
B = ContentFilter.of(BOB)
ALL = ContentFilter.everyone()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repos(request: pytest.FixtureRequest) -> GraphRepos:
    """The same scenarios run against both graph adapters."""
    if request.param == "in_memory":
        return GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
    return build_graph_repos(request.getfixturevalue("db_session"))


async def _node(repos: GraphRepos, owner: uuid.UUID) -> Node:
    node = Node.create(owner_id=owner, name="Item", type=None)
    await repos.nodes.add(node)
    return node


async def test_own_item_is_attachable_and_foreign_item_is_not(
    repos: GraphRepos,
) -> None:
    """A can attach to A's item; B cannot; the system scope can."""
    node = await _node(repos, ALICE)
    access = GraphAttachTargetAccess(repos)

    assert await access.can_attach(AttachmentTarget.NODE, node.id, A)
    assert await access.can_attach(AttachmentTarget.NODE, node.id, ALL)
    assert not await access.can_attach(AttachmentTarget.NODE, node.id, B)


async def test_missing_and_deleted_items_are_not_attachable(
    repos: GraphRepos,
) -> None:
    """Unknown and soft-deleted items answer False, like a foreign one."""
    node = await _node(repos, ALICE)
    node.soft_delete()
    await repos.nodes.save(node)
    access = GraphAttachTargetAccess(repos)

    assert not await access.can_attach(AttachmentTarget.NODE, node.id, A)
    assert not await access.can_attach(AttachmentTarget.NODE, uuid.uuid7(), A)


async def test_edge_targets_follow_the_edge_owner(repos: GraphRepos) -> None:
    """Connections are checked in the edge repository, not the node one."""
    source, target = await _node(repos, ALICE), await _node(repos, ALICE)
    edge = Edge.create(
        owner_id=ALICE, source_id=source.id, target_id=target.id, type="knows"
    )
    await repos.edges.add(edge)
    access = GraphAttachTargetAccess(repos)

    assert await access.can_attach(AttachmentTarget.EDGE, edge.id, A)
    assert not await access.can_attach(AttachmentTarget.EDGE, edge.id, B)
    # An item id is not a connection id.
    assert not await access.can_attach(AttachmentTarget.EDGE, source.id, A)
    assert not await access.can_attach(AttachmentTarget.NODE, edge.id, A)
