from typing import Annotated

from fastapi import Depends

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.application.create_node import CreateNode
from app.modules.graph.application.get_node import GetNode
from app.modules.graph.application.list_nodes import ListNodes
from app.modules.graph.ports.node_repository import NodeRepository
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork

_graph_repos = GraphRepos(nodes=InMemoryNodeRepository())
"""Process-wide graph repositories.

A module-level singleton for now, since the in-memory store must survive
across requests - the SQLAlchemy adapter replaces this with a per-request
session instead, once that adapter exists.
"""


def get_graph_repos() -> GraphRepos:
    """Return the process-wide graph repository bundle."""
    return _graph_repos


def get_node_repository(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
) -> NodeRepository:
    """Return the node repository directly, for read-only queries."""
    return repos.nodes


def get_graph_uow(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
) -> GraphUnitOfWork:
    """Return a unit of work over the shared graph repositories, for commands."""
    return create_in_memory_graph_uow(repos)


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
