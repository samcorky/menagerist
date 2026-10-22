from typing import TYPE_CHECKING, Any

from app.modules.graph.application.claim_orphaned_items import ClaimOrphanedItems
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
from app.modules.graph.application.delete_unused_node_type import DeleteUnusedNodeType
from app.modules.graph.application.get_edge import GetEdge
from app.modules.graph.application.get_edge_type import GetEdgeType
from app.modules.graph.application.get_node import GetNode
from app.modules.graph.application.get_node_type import GetNodeType
from app.modules.graph.application.list_attribute_values import ListAttributeValues
from app.modules.graph.application.list_edge_types import ListEdgeTypes
from app.modules.graph.application.list_edges import ListEdges
from app.modules.graph.application.list_item_fields import ListItemFields
from app.modules.graph.application.list_node_types import ListNodeTypes
from app.modules.graph.application.list_nodes import ListNodes
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.promote_extra_schema_field import (
    PromoteExtraSchemaField,
)
from app.modules.graph.application.purge_edge_type_attribute import (
    PurgeEdgeTypeAttribute,
)
from app.modules.graph.application.purge_node_type_attribute import (
    PurgeNodeTypeAttribute,
)
from app.modules.graph.application.search_nodes import SearchNodes
from app.modules.graph.application.update_edge import UpdateEdge
from app.modules.graph.application.update_edge_type import UpdateEdgeType
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.application.update_node_type import UpdateNodeType
from app.modules.graph.application.validate_query import ValidateQuery
from app.shared_kernel.access import Access, Content, Requires, System

if TYPE_CHECKING:
    from app.shared_kernel.cqrs import UseCase

ITEM_STANCES: dict[type[UseCase[Any, Any]], Access] = {
    GetNode: Content(GraphPermission.ITEM_READ),
    ListNodes: Content(GraphPermission.ITEM_READ),
    SearchNodes: Content(GraphPermission.ITEM_READ),
    GetEdge: Content(GraphPermission.ITEM_READ),
    ListEdges: Content(GraphPermission.ITEM_READ),
    ListAttributeValues: Content(GraphPermission.ITEM_READ),
    ListItemFields: Content(GraphPermission.ITEM_READ),
    CountNodeTypeAttributeUsage: Content(GraphPermission.ITEM_READ),
    CountEdgeTypeAttributeUsage: Content(GraphPermission.ITEM_READ),
    CreateNode: Content(GraphPermission.ITEM_WRITE),
    UpdateNode: Content(GraphPermission.ITEM_WRITE),
    DeleteNode: Content(GraphPermission.ITEM_WRITE),
    CreateEdge: Content(GraphPermission.ITEM_WRITE),
    CreateEdges: Content(GraphPermission.ITEM_WRITE),
    UpdateEdge: Content(GraphPermission.ITEM_WRITE),
    DeleteEdge: Content(GraphPermission.ITEM_WRITE),
    PromoteExtraSchemaField: Content(GraphPermission.TYPE_WRITE),
}


VOCABULARY_STANCES: dict[type[UseCase[Any, Any]], Access] = {
    GetNodeType: Requires(GraphPermission.TYPE_READ),
    ListNodeTypes: Requires(GraphPermission.TYPE_READ),
    GetEdgeType: Requires(GraphPermission.TYPE_READ),
    ListEdgeTypes: Requires(GraphPermission.TYPE_READ),
    ValidateQuery: Requires(GraphPermission.TYPE_READ),
    CreateNodeType: Requires(GraphPermission.TYPE_WRITE),
    UpdateNodeType: Requires(GraphPermission.TYPE_WRITE),
    CreateEdgeType: Requires(GraphPermission.TYPE_WRITE),
    UpdateEdgeType: Requires(GraphPermission.TYPE_WRITE),
}


def test_item_use_cases_need_the_item_permissions() -> None:
    """Each person sees and changes only their own content, given the permission."""
    assert {use_case: use_case.access for use_case in ITEM_STANCES} == ITEM_STANCES


def test_claim_jobs_are_system_only() -> None:
    """Only the system actor hands pre-account content to the first owner."""
    for use_case in (ClaimOrphanedItems,):
        assert use_case.access == System()


def test_shared_vocabulary_needs_the_type_permissions() -> None:
    """Item and relationship types are shared, read or written by permission."""
    assert {u: u.access for u in VOCABULARY_STANCES} == VOCABULARY_STANCES


def test_structural_changes_keep_their_permissions() -> None:
    """Deleting or purging type structure stays admin-only."""
    assert {
        DeleteEdgeType: DeleteEdgeType.access,
        DeleteNodeType: DeleteNodeType.access,
        DeleteUnusedNodeType: DeleteUnusedNodeType.access,
        PurgeEdgeTypeAttribute: PurgeEdgeTypeAttribute.access,
        PurgeNodeTypeAttribute: PurgeNodeTypeAttribute.access,
    } == {
        DeleteEdgeType: Requires(GraphPermission.DELETE_EDGE_TYPE),
        DeleteNodeType: Requires(GraphPermission.DELETE_NODE_TYPE),
        DeleteUnusedNodeType: Requires(GraphPermission.DELETE_NODE_TYPE),
        PurgeEdgeTypeAttribute: Requires(GraphPermission.PURGE_EDGE_TYPE_ATTRIBUTE),
        PurgeNodeTypeAttribute: Requires(GraphPermission.PURGE_NODE_TYPE_ATTRIBUTE),
    }
