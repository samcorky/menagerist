from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.graph.adapters.persistence.unit_of_work import create_graph_uow
from app.modules.graph.application.create_edge import CreateEdge
from app.modules.graph.application.create_edge_type import CreateEdgeType
from app.modules.graph.application.create_node import CreateNode
from app.modules.graph.application.create_node_type import CreateNodeType
from app.modules.graph.application.delete_edge import DeleteEdge
from app.modules.graph.application.delete_edge_type import DeleteEdgeType
from app.modules.graph.application.delete_node import DeleteNode
from app.modules.graph.application.delete_node_type import DeleteNodeType
from app.modules.graph.application.get_edge import GetEdge
from app.modules.graph.application.get_edge_type import GetEdgeType
from app.modules.graph.application.get_node import GetNode
from app.modules.graph.application.get_node_type import GetNodeType
from app.modules.graph.application.list_edge_types import ListEdgeTypes
from app.modules.graph.application.list_edges import ListEdges
from app.modules.graph.application.list_node_types import ListNodeTypes
from app.modules.graph.application.list_nodes import ListNodes
from app.modules.graph.application.update_edge import UpdateEdge
from app.modules.graph.application.update_edge_type import UpdateEdgeType
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.application.update_node_type import UpdateNodeType
from app.modules.graph.ports.edge_repository import EdgeRepository
from app.modules.graph.ports.edge_type_repository import EdgeTypeRepository
from app.modules.graph.ports.node_repository import NodeRepository
from app.modules.graph.ports.node_type_repository import NodeTypeRepository
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


async def get_node_type_repository(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> AsyncIterator[NodeTypeRepository]:
    """Return the node type repository directly, for read-only queries."""
    async with uow as repos:
        yield repos.node_types


async def get_edge_type_repository(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> AsyncIterator[EdgeTypeRepository]:
    """Return the edge type repository directly, for read-only queries."""
    async with uow as repos:
        yield repos.edge_types


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


def get_create_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> CreateNodeType:
    """Return the `CreateNodeType` use case."""
    return CreateNodeType(uow)


def get_get_node_type_use_case(
    node_types: Annotated[NodeTypeRepository, Depends(get_node_type_repository)],
) -> GetNodeType:
    """Return the `GetNodeType` use case."""
    return GetNodeType(node_types)


def get_list_node_types_use_case(
    node_types: Annotated[NodeTypeRepository, Depends(get_node_type_repository)],
) -> ListNodeTypes:
    """Return the `ListNodeTypes` use case."""
    return ListNodeTypes(node_types)


def get_update_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> UpdateNodeType:
    """Return the `UpdateNodeType` use case."""
    return UpdateNodeType(uow)


def get_delete_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> DeleteNodeType:
    """Return the `DeleteNodeType` use case."""
    return DeleteNodeType(uow)


def get_create_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> CreateEdgeType:
    """Return the `CreateEdgeType` use case."""
    return CreateEdgeType(uow)


def get_get_edge_type_use_case(
    edge_types: Annotated[EdgeTypeRepository, Depends(get_edge_type_repository)],
) -> GetEdgeType:
    """Return the `GetEdgeType` use case."""
    return GetEdgeType(edge_types)


def get_list_edge_types_use_case(
    edge_types: Annotated[EdgeTypeRepository, Depends(get_edge_type_repository)],
) -> ListEdgeTypes:
    """Return the `ListEdgeTypes` use case."""
    return ListEdgeTypes(edge_types)


def get_update_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> UpdateEdgeType:
    """Return the `UpdateEdgeType` use case."""
    return UpdateEdgeType(uow)


def get_delete_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> DeleteEdgeType:
    """Return the `DeleteEdgeType` use case."""
    return DeleteEdgeType(uow)
