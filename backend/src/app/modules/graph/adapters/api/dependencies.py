from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.choice_list_source import (
    PresetChoiceListSource,
    get_choice_list_source,
)
from app.entrypoints.api.shared.collection_members import (
    CollectionsMembers,
    get_collection_members,
)
from app.entrypoints.api.shared.dependencies import (
    get_access_policy,
    get_authorization_port,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_graph_repos,
    create_graph_uow,
)
from app.modules.graph.application.count_edge_type_attribute_usage import (
    CountEdgeTypeAttributeUsage,
)
from app.modules.graph.application.count_node_type_attribute_usage import (
    CountNodeTypeAttributeUsage,
)
from app.modules.graph.application.create_edge import CreateEdge
from app.modules.graph.application.create_edge_type import CreateEdgeType
from app.modules.graph.application.create_edges import CreateEdges
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
from app.modules.graph.application.list_attribute_values import ListAttributeValues
from app.modules.graph.application.list_edge_types import ListEdgeTypes
from app.modules.graph.application.list_edges import ListEdges
from app.modules.graph.application.list_node_types import ListNodeTypes
from app.modules.graph.application.list_nodes import ListNodes
from app.modules.graph.application.promote_extra_schema_field import (
    PromoteExtraSchemaField,
)
from app.modules.graph.application.purge_edge_type_attribute import (
    PurgeEdgeTypeAttribute,
)
from app.modules.graph.application.purge_node_type_attribute import (
    PurgeNodeTypeAttribute,
)
from app.modules.graph.application.update_edge import UpdateEdge
from app.modules.graph.application.update_edge_type import UpdateEdgeType
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.application.update_node_type import UpdateNodeType
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.platform.database import get_session_factory
from app.shared_kernel.access_policy import AccessPolicy
from app.shared_kernel.authorization import AuthorizationPort

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_graph_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> GraphUnitOfWork:
    """Return a unit of work over the graph tables, for commands."""
    return create_graph_uow(session_factory)


async def get_graph_repos(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[GraphRepos]:
    """Return a read-only repository bundle over the graph tables, for queries."""
    async with session_factory() as session:
        yield build_graph_repos(session)


def get_create_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> CreateNode:
    return CreateNode(uow, policy, choice_lists)


def get_get_node_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> GetNode:
    return GetNode(repos, policy)


def get_list_nodes_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    collection_members: Annotated[CollectionsMembers, Depends(get_collection_members)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> ListNodes:
    return ListNodes(repos, policy, collection_members)


def get_update_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> UpdateNode:
    return UpdateNode(uow, policy, choice_lists)


def get_delete_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> DeleteNode:
    return DeleteNode(uow, policy)


def get_promote_extra_schema_field_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> PromoteExtraSchemaField:
    return PromoteExtraSchemaField(uow, policy)


def get_create_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> CreateEdge:
    return CreateEdge(uow, policy, choice_lists)


def get_create_edges_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> CreateEdges:
    return CreateEdges(uow, policy, choice_lists)


def get_get_edge_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> GetEdge:
    return GetEdge(repos, policy)


def get_list_edges_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> ListEdges:
    return ListEdges(repos, policy)


def get_update_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> UpdateEdge:
    return UpdateEdge(uow, policy, choice_lists)


def get_delete_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> DeleteEdge:
    return DeleteEdge(uow, policy)


def get_create_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> CreateNodeType:
    return CreateNodeType(uow, choice_lists)


def get_get_node_type_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> GetNodeType:
    return GetNodeType(repos, choice_lists)


def get_list_node_types_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> ListNodeTypes:
    return ListNodeTypes(repos, choice_lists)


def get_update_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> UpdateNodeType:
    return UpdateNodeType(uow, choice_lists)


def get_delete_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    authorization: Annotated[AuthorizationPort, Depends(get_authorization_port)],
) -> DeleteNodeType:
    return DeleteNodeType(uow, authorization)


def get_create_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> CreateEdgeType:
    return CreateEdgeType(uow, choice_lists)


def get_get_edge_type_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> GetEdgeType:
    return GetEdgeType(repos, choice_lists)


def get_list_edge_types_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> ListEdgeTypes:
    return ListEdgeTypes(repos, choice_lists)


def get_update_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> UpdateEdgeType:
    return UpdateEdgeType(uow, choice_lists)


def get_delete_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    authorization: Annotated[AuthorizationPort, Depends(get_authorization_port)],
) -> DeleteEdgeType:
    return DeleteEdgeType(uow, authorization)


def get_count_node_type_attribute_usage_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> CountNodeTypeAttributeUsage:
    return CountNodeTypeAttributeUsage(repos, policy)


def get_purge_node_type_attribute_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    authorization: Annotated[AuthorizationPort, Depends(get_authorization_port)],
) -> PurgeNodeTypeAttribute:
    return PurgeNodeTypeAttribute(uow, authorization)


def get_list_attribute_values_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> ListAttributeValues:
    return ListAttributeValues(repos, policy)


def get_count_edge_type_attribute_usage_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> CountEdgeTypeAttributeUsage:
    return CountEdgeTypeAttributeUsage(repos, policy)


def get_purge_edge_type_attribute_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    authorization: Annotated[AuthorizationPort, Depends(get_authorization_port)],
) -> PurgeEdgeTypeAttribute:
    return PurgeEdgeTypeAttribute(uow, authorization)
