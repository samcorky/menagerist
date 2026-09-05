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
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_graph_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> GraphUnitOfWork:
    """Return a unit of work over the graph tables, for commands and queries alike."""
    return create_graph_uow(session_factory)


def get_create_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> CreateNode:
    return CreateNode(uow)


def get_get_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> GetNode:
    return GetNode(uow)


def get_list_nodes_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> ListNodes:
    return ListNodes(uow)


def get_update_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> UpdateNode:
    return UpdateNode(uow)


def get_delete_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> DeleteNode:
    return DeleteNode(uow)


def get_create_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> CreateEdge:
    return CreateEdge(uow)


def get_get_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> GetEdge:
    return GetEdge(uow)


def get_list_edges_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> ListEdges:
    return ListEdges(uow)


def get_update_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> UpdateEdge:
    return UpdateEdge(uow)


def get_delete_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> DeleteEdge:
    return DeleteEdge(uow)


def get_create_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> CreateNodeType:
    return CreateNodeType(uow)


def get_get_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> GetNodeType:
    return GetNodeType(uow)


def get_list_node_types_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> ListNodeTypes:
    return ListNodeTypes(uow)


def get_update_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> UpdateNodeType:
    return UpdateNodeType(uow)


def get_delete_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> DeleteNodeType:
    return DeleteNodeType(uow)


def get_create_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> CreateEdgeType:
    return CreateEdgeType(uow)


def get_get_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> GetEdgeType:
    return GetEdgeType(uow)


def get_list_edge_types_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> ListEdgeTypes:
    return ListEdgeTypes(uow)


def get_update_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> UpdateEdgeType:
    return UpdateEdgeType(uow)


def get_delete_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
) -> DeleteEdgeType:
    return DeleteEdgeType(uow)
