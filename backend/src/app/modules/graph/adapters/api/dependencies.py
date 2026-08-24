from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.graph.adapters.persistence.unit_of_work import create_graph_uow
from app.modules.graph.application.create_edge import CreateEdge
from app.modules.graph.application.create_node import CreateNode
from app.modules.graph.application.delete_edge import DeleteEdge
from app.modules.graph.application.delete_node import DeleteNode
from app.modules.graph.application.get_edge import GetEdge
from app.modules.graph.application.get_node import GetNode
from app.modules.graph.application.list_edges import ListEdges
from app.modules.graph.application.list_nodes import ListNodes
from app.modules.graph.application.update_edge import UpdateEdge
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.ports.edge_repository import EdgeRepository
from app.modules.graph.ports.node_repository import NodeRepository
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_graph_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> GraphUnitOfWork:
    """Return a unit of work over the graph tables, for commands and queries alike."""
    return create_graph_uow(session_factory)


async def get_node_repository(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> AsyncIterator[NodeRepository]:
    """Return the node repository directly, for read-only queries.

    Reuses the unit of work's session lifecycle rather than opening a second,
    separate per-request session - a read simply never calls `.commit()`.
    """
    async with uow as repos:
        yield repos.nodes


async def get_edge_repository(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> AsyncIterator[EdgeRepository]:
    """Return the edge repository directly, for read-only queries.

    Reuses the unit of work's session lifecycle rather than opening a second,
    separate per-request session - a read simply never calls `.commit()`.
    """
    async with uow as repos:
        yield repos.edges


def get_create_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> CreateNode:
    """Return the `CreateNode` use case."""
    return CreateNode(uow)


def get_get_node_use_case(
    nodes: Annotated[NodeRepository, Depends(get_node_repository)],
) -> GetNode:
    """Return the `GetNode` use case."""
    return GetNode(nodes)


def get_list_nodes_use_case(
    nodes: Annotated[NodeRepository, Depends(get_node_repository)],
) -> ListNodes:
    """Return the `ListNodes` use case."""
    return ListNodes(nodes)


def get_update_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> UpdateNode:
    """Return the `UpdateNode` use case."""
    return UpdateNode(uow)


def get_delete_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> DeleteNode:
    """Return the `DeleteNode` use case."""
    return DeleteNode(uow)


def get_create_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> CreateEdge:
    """Return the `CreateEdge` use case."""
    return CreateEdge(uow)


def get_get_edge_use_case(
    edges: Annotated[EdgeRepository, Depends(get_edge_repository)],
) -> GetEdge:
    """Return the `GetEdge` use case."""
    return GetEdge(edges)


def get_list_edges_use_case(
    edges: Annotated[EdgeRepository, Depends(get_edge_repository)],
) -> ListEdges:
    """Return the `ListEdges` use case."""
    return ListEdges(edges)


def get_update_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> UpdateEdge:
    """Return the `UpdateEdge` use case."""
    return UpdateEdge(uow)


def get_delete_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> DeleteEdge:
    """Return the `DeleteEdge` use case."""
    return DeleteEdge(uow)
