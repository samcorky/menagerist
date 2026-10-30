from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.choice_list_source import (
    PresetChoiceListSource,
    get_choice_list_source,
)
from app.entrypoints.api.shared.bridges.collection_conditions import (
    build_search_graph_repos,
)
from app.entrypoints.api.shared.bridges.collection_members import (
    CollectionsMembers,
    get_collection_members,
)
from app.entrypoints.api.shared.bridges.item_dependents import (
    ItemDependentsPurger,
    get_item_dependents,
)
from app.modules.graph.adapters.persistence.unit_of_work import create_graph_uow
from app.modules.graph.application.count_edge_type_attribute_usage import (
    CountEdgeTypeAttributeUsage,
)
from app.modules.graph.application.count_node_type_attribute_usage import (
    CountNodeTypeAttributeUsage,
)
from app.modules.graph.application.count_node_types import CountNodeTypes
from app.modules.graph.application.count_nodes import CountNodes
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
from app.modules.graph.application.list_deleted_nodes import ListDeletedNodes
from app.modules.graph.application.list_edge_types import ListEdgeTypes
from app.modules.graph.application.list_edges import ListEdges
from app.modules.graph.application.list_item_fields import ListItemFields
from app.modules.graph.application.list_node_types import ListNodeTypes
from app.modules.graph.application.list_nodes import ListNodes
from app.modules.graph.application.promote_extra_schema_field import (
    PromoteExtraSchemaField,
)
from app.modules.graph.application.purge_deleted_node import PurgeDeletedNode
from app.modules.graph.application.purge_edge_type_attribute import (
    PurgeEdgeTypeAttribute,
)
from app.modules.graph.application.purge_node_type_attribute import (
    PurgeNodeTypeAttribute,
)
from app.modules.graph.application.random_node import RandomNode
from app.modules.graph.application.restore_node import RestoreNode
from app.modules.graph.application.search_node_counts import SearchNodeCounts
from app.modules.graph.application.search_nodes import SearchNodes
from app.modules.graph.application.update_edge import UpdateEdge
from app.modules.graph.application.update_edge_type import UpdateEdgeType
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.application.update_node_type import UpdateNodeType
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.platform.database import get_session_factory
from app.shared_kernel.access_guard import AccessGuard

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
        yield build_search_graph_repos(session)


def get_create_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CreateNode:
    return CreateNode(uow, guard, choice_lists)


def get_get_node_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetNode:
    return GetNode(repos, guard)


def get_list_nodes_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    collection_members: Annotated[CollectionsMembers, Depends(get_collection_members)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListNodes:
    return ListNodes(repos, guard, collection_members)


def get_random_node_use_case(
    list_nodes: Annotated[ListNodes, Depends(get_list_nodes_use_case)],
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RandomNode:
    return RandomNode(repos, guard, list_nodes)


def get_count_nodes_use_case(
    list_nodes: Annotated[ListNodes, Depends(get_list_nodes_use_case)],
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CountNodes:
    return CountNodes(repos, guard, list_nodes)


def get_search_nodes_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> SearchNodes:
    return SearchNodes(repos, guard)


def get_search_node_counts_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> SearchNodeCounts:
    return SearchNodeCounts(repos, guard)


def get_count_node_types_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CountNodeTypes:
    return CountNodeTypes(repos, guard)


def get_list_item_fields_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListItemFields:
    return ListItemFields(repos, guard)


def get_update_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> UpdateNode:
    return UpdateNode(uow, guard, choice_lists)


def get_delete_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> DeleteNode:
    return DeleteNode(uow, guard)


def get_list_deleted_nodes_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListDeletedNodes:
    return ListDeletedNodes(repos, guard)


def get_restore_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> RestoreNode:
    return RestoreNode(uow, guard)


def get_purge_deleted_node_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    dependents: Annotated[ItemDependentsPurger, Depends(get_item_dependents)],
) -> PurgeDeletedNode:
    return PurgeDeletedNode(uow, guard, dependents)


def get_promote_extra_schema_field_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> PromoteExtraSchemaField:
    return PromoteExtraSchemaField(uow, guard)


def get_create_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> CreateEdge:
    return CreateEdge(uow, guard, choice_lists)


def get_create_edges_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> CreateEdges:
    return CreateEdges(uow, guard, choice_lists)


def get_get_edge_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetEdge:
    return GetEdge(repos, guard)


def get_list_edges_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListEdges:
    return ListEdges(repos, guard)


def get_update_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
) -> UpdateEdge:
    return UpdateEdge(uow, guard, choice_lists)


def get_delete_edge_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> DeleteEdge:
    return DeleteEdge(uow, guard)


def get_create_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CreateNodeType:
    return CreateNodeType(uow, guard, choice_lists)


def get_get_node_type_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetNodeType:
    return GetNodeType(repos, guard, choice_lists)


def get_list_node_types_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListNodeTypes:
    return ListNodeTypes(repos, guard, choice_lists)


def get_update_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> UpdateNodeType:
    return UpdateNodeType(uow, guard, choice_lists)


def get_delete_node_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> DeleteNodeType:
    return DeleteNodeType(uow, guard)


def get_create_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CreateEdgeType:
    return CreateEdgeType(uow, guard, choice_lists)


def get_get_edge_type_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetEdgeType:
    return GetEdgeType(repos, guard, choice_lists)


def get_list_edge_types_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListEdgeTypes:
    return ListEdgeTypes(repos, guard, choice_lists)


def get_update_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    choice_lists: Annotated[PresetChoiceListSource, Depends(get_choice_list_source)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> UpdateEdgeType:
    return UpdateEdgeType(uow, guard, choice_lists)


def get_delete_edge_type_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> DeleteEdgeType:
    return DeleteEdgeType(uow, guard)


def get_count_node_type_attribute_usage_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CountNodeTypeAttributeUsage:
    return CountNodeTypeAttributeUsage(repos, guard)


def get_purge_node_type_attribute_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> PurgeNodeTypeAttribute:
    return PurgeNodeTypeAttribute(uow, guard)


def get_list_attribute_values_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListAttributeValues:
    return ListAttributeValues(repos, guard)


def get_count_edge_type_attribute_usage_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> CountEdgeTypeAttributeUsage:
    return CountEdgeTypeAttributeUsage(repos, guard)


def get_purge_edge_type_attribute_use_case(
    uow: Annotated[GraphUnitOfWork, Depends(get_graph_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> PurgeEdgeTypeAttribute:
    return PurgeEdgeTypeAttribute(uow, guard)
