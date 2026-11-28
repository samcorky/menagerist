import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.conditional_request import (
    ConditionalGetDep,
    ConditionalPatchDep,
)
from app.entrypoints.api.shared.http.http_headers import (
    conditional_get_responses,
    conditional_patch_responses,
    link_next_header,
    set_next_link,
    set_page_headers,
)
from app.entrypoints.api.shared.http.parameters import (
    FieldKey,
    NewestFirstSearchPageParams,
    NodeId,
    PageAfter,
    PageLimit,
    PageParams,
)
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.http.rate_limit import (
    RATE_LIMITED_RESPONSE,
    RateLimitBucket,
    rate_limited,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.graph.adapters.api.dependencies import (
    get_count_node_types_use_case,
    get_count_nodes_use_case,
    get_create_node_use_case,
    get_delete_node_use_case,
    get_delete_nodes_use_case,
    get_duplicate_node_use_case,
    get_get_item_path_use_case,
    get_get_node_use_case,
    get_list_deleted_nodes_use_case,
    get_list_item_contents_use_case,
    get_list_item_fields_use_case,
    get_list_nodes_use_case,
    get_promote_extra_schema_field_use_case,
    get_purge_deleted_node_use_case,
    get_random_node_use_case,
    get_restore_node_use_case,
    get_search_node_counts_use_case,
    get_search_nodes_use_case,
    get_tag_nodes_use_case,
    get_update_node_use_case,
)
from app.modules.graph.adapters.api.node.schemas import (
    CreateNodeRequest,
    DeletedNodeResponse,
    DeleteNodesRequest,
    DuplicateNodeRequest,
    ItemFieldResponse,
    NodeContentsEntryResponse,
    NodeCountResponse,
    NodeResponse,
    NodeSearchCountsRequest,
    NodeSearchCountsResponse,
    NodeSearchRequest,
    NodeSearchResponse,
    NodeTypeCountResponse,
    PromotedItemFieldResponse,
    PromoteExtraSchemaFieldRequest,
    TagNodesRequest,
    TagNodesResponse,
    UpdateNodeRequest,
)
from app.modules.graph.adapters.api.node_type.schemas import NodeTypeResponse
from app.modules.graph.application.count_node_types import (
    CountNodeTypes,
    CountNodeTypesQuery,
)
from app.modules.graph.application.count_nodes import CountNodes
from app.modules.graph.application.create_node import CreateNode
from app.modules.graph.application.delete_node import DeleteNode, DeleteNodeCommand
from app.modules.graph.application.delete_nodes import DeleteNodes
from app.modules.graph.application.duplicate_node import DuplicateNode
from app.modules.graph.application.get_item_path import GetItemPath, GetItemPathQuery
from app.modules.graph.application.get_node import GetNode, GetNodeQuery
from app.modules.graph.application.list_deleted_nodes import (
    DeletedNodeSort,
    ListDeletedNodes,
    ListDeletedNodesQuery,
)
from app.modules.graph.application.list_item_contents import (
    ListItemContents,
    ListItemContentsQuery,
)
from app.modules.graph.application.list_item_fields import (
    ListItemFields,
    ListItemFieldsQuery,
)
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery, NodeSort
from app.modules.graph.application.promote_extra_schema_field import (
    PromoteExtraSchemaField,
    PromoteExtraSchemaFieldCommand,
)
from app.modules.graph.application.purge_deleted_node import (
    PurgeDeletedNode,
    PurgeDeletedNodeCommand,
)
from app.modules.graph.application.random_node import RandomNode
from app.modules.graph.application.restore_node import RestoreNode, RestoreNodeCommand
from app.modules.graph.application.search_node_counts import (
    SearchNodeCounts,
    SearchNodeCountsQuery,
)
from app.modules.graph.application.search_nodes import SearchNodes, SearchNodesQuery
from app.modules.graph.application.tag_nodes import TagNodes
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.domain.errors import (
    CollectionNotFoundError,
    EdgeTypeNotFoundError,
    InvalidSchemaError,
    NodeNotFoundError,
    NodeTypeDeletedError,
    NodeTypeNotFoundError,
    RelationshipHoldsNothingError,
)
from app.modules.graph.domain.query import InvalidQueryError
from app.modules.graph.domain.reach import InvalidReachDepthError, ReachTooLargeError
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ValidationError

router = APIRouter(prefix="/nodes", tags=["Nodes"], route_class=PermissionAwareRoute)


def _viewer_state(favourite: bool) -> str:
    """The part of an item's ETag that depends on who is looking.

    Favouriting changes neither `updated_at` nor the item, only the viewer's copy.
    """
    return "favourite" if favourite else "plain"


_TOTAL_COUNT_HEADERS: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            "Link": {
                "description": "RFC 8288 next-page cursor. Absent on last page.",
                "schema": {"type": "string"},
            },
            "Total-Count": {
                "description": (
                    "Items matching the filters. Exact, except with `q`, where it "
                    + "stops at 1000 (see `Total-Count-Capped`)."
                ),
                "schema": {"type": "integer"},
            },
            "Total-Count-Capped": {
                "description": (
                    "`true` when `q` matched more than 1000 items, so `Total-Count` "
                    + "is 1000 and a lower bound. Absent otherwise."
                ),
                "schema": {"type": "string", "enum": ["true"]},
            },
        }
    }
}

_DELETED_HEADERS: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            "Link": {
                "description": "RFC 8288 next-page cursor. Absent on last page.",
                "schema": {"type": "string"},
            },
            "Total-Count": {
                "description": "Deleted items in total. Always exact.",
                "schema": {"type": "integer"},
            },
        },
        "links": {
            "RestoreNode": {
                "operationId": "restore_node",
                "parameters": {"node_id": "$response.body#/0/id"},
                "description": "Restore the most recently deleted one in this list.",
            },
            "PurgeNode": {
                "operationId": "purge_node",
                "parameters": {"node_id": "$response.body#/0/id"},
                "description": "Permanently delete the most recently deleted one.",
            },
        },
    }
}

# The most ids one list read takes: a page, so that all of them can come back at once.
MAX_IDS = 100

_Q_DESCRIPTION = "Search text, matched case-insensitively."
_Q_DESCRIPTION += " Looks in the name, the description and every text or number"
_Q_DESCRIPTION += " value in the item's details. Field names, yes/no values, ratings,"
_Q_DESCRIPTION += " removed fields and fields excluded from search are not searched."


@dataclass
class NodeFilters:
    """Query parameters that choose which items a list or count covers."""

    type: Annotated[
        str | None, Query(description="Keep items of the item type with this slug.")
    ] = None
    q: Annotated[str | None, Query(description=_Q_DESCRIPTION)] = None
    favourite: Annotated[
        bool | None, Query(description="Keep only favourites, or only the rest.")
    ] = None
    collection: Annotated[
        uuid.UUID | None,
        Query(
            description=(
                "Restrict the list to items on this collection. For a smart "
                + "collection, the items matching its definition, still in id order."
            )
        ),
    ] = None


NodeFiltersDep = Annotated[NodeFilters, Depends()]


@router.post(
    "",
    response_model=NodeResponse,
    status_code=201,
    operation_id="create_node",
    responses=error_response(ValidationError, detail="type must be provided"),
)
async def create_node(
    payload: CreateNodeRequest,
    use_case: Annotated[CreateNode, Depends(get_create_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse:
    """Create a new node."""
    node = await use_case.handle(payload.to_command(), actor)
    return NodeResponse.from_domain(node)


@router.post(
    "/search",
    response_model=NodeSearchResponse,
    operation_id="search_nodes",
    dependencies=[Depends(rate_limited(RateLimitBucket.SEARCH))],
    responses={
        **RATE_LIMITED_RESPONSE,
        **error_response(
            InvalidQueryError, detail="where.children[0]: Unknown condition kind."
        ),
    },
)
async def search_nodes(
    body: NodeSearchRequest,
    use_case: Annotated[SearchNodes, Depends(get_search_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeSearchResponse:
    """Search items with a condition tree, paged by cursor.

    `query` is `{"v": 1, "where": <group>, "sort": [...]}`. A group is
    `{"op": "and" | "or" | "not", "children": [...]}` of conditions and groups.
    A field condition's `!=` and `not_in` (a list, like `in`) match only items
    of its `type`, including those where the field is missing. A condition
    that refers to a removed field matches nothing (so under
    `not` it matches everything) and is reported in `warnings`. A malformed
    query is a 400 whose `detail` names the JSON path.
    """
    result = await use_case.handle(
        SearchNodesQuery(query=body.query, limit=body.limit, cursor=body.cursor),
        actor,
    )
    return NodeSearchResponse.from_result(result)


@router.post(
    "/search/counts",
    response_model=NodeSearchCountsResponse,
    operation_id="count_node_searches",
    dependencies=[Depends(rate_limited(RateLimitBucket.SEARCH))],
    responses={
        **RATE_LIMITED_RESPONSE,
        **error_response(
            InvalidQueryError,
            detail="queries.no_photo: where.children[0]: Unknown condition kind.",
        ),
    },
)
async def count_node_searches(
    body: NodeSearchCountsRequest,
    use_case: Annotated[SearchNodeCounts, Depends(get_search_node_counts_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeSearchCountsResponse:
    """Count the items several condition trees match, in one call.

    Each entry in `queries` is a condition tree like the `query` of
    `POST /node/search`, and is parsed and resolved the same way, so a count
    always agrees with the list a search for that query returns. Sort keys are
    checked but do not change a count. `total` is exact up to 100,000, then
    `total_capped` is true. A malformed query is a 400 whose `detail` starts
    `queries.<name>`.
    """
    result = await use_case.handle(SearchNodeCountsQuery(queries=body.queries), actor)
    return NodeSearchCountsResponse.from_result(result)


@router.get(
    "/fields",
    response_model=list[ItemFieldResponse],
    operation_id="list_item_fields",
)
async def list_item_fields(
    use_case: Annotated[ListItemFields, Depends(get_list_item_fields_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    type: Annotated[
        str | None,
        Query(description="Count only items of the item type with this slug."),
    ] = None,
) -> list[ItemFieldResponse]:
    """List the fields your items carry themselves, most used first.

    These are the per-item fields a search can filter on. A field appears once
    per name and kind, with how many of your items declare it. Removed fields
    and fields without a recorded kind are left out. At most 200 are returned.
    """
    fields = await use_case.handle(ListItemFieldsQuery(type_slug=type), actor)
    return [ItemFieldResponse.from_domain(field) for field in fields]


@router.post(
    "/fields/{key}/promote",
    response_model=PromotedItemFieldResponse,
    operation_id="promote_item_field",
    responses={
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(
            InvalidSchemaError,
            detail="2 items keep Signed as a different kind of field.",
        ),
    },
)
async def promote_item_field(
    key: FieldKey,
    payload: PromoteExtraSchemaFieldRequest,
    use_case: Annotated[
        PromoteExtraSchemaField, Depends(get_promote_extra_schema_field_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> PromotedItemFieldResponse:
    """Make a field your items carry themselves a field of their item type.

    Every item of the type that defines the field loses its own copy, in one
    change, and keeps its value. The definition most of them share is used, with
    the choices of all of them. Refused when some define it as another kind.
    """
    promoted = await use_case.handle(
        PromoteExtraSchemaFieldCommand(node_type_id=payload.node_type_id, key=key),
        actor,
    )
    return PromotedItemFieldResponse(
        items=promoted.items,
        node_type=NodeTypeResponse.from_domain(promoted.node_type),
    )


@router.get(
    "/deleted",
    response_model=list[DeletedNodeResponse],
    operation_id="list_deleted_nodes",
    responses=_DELETED_HEADERS,
)
async def list_deleted_nodes(
    use_case: Annotated[ListDeletedNodes, Depends(get_list_deleted_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    page: Annotated[NewestFirstSearchPageParams[DeletedNodeSort], Query()],
) -> list[DeletedNodeResponse]:
    """List your deleted items, newest deleted first unless `sort` or `order` say.

    An item that has since been restored or purged does not stop the next page: the
    `Link` header's cursor holds the position, not the row.
    """
    result = await use_case.handle(
        ListDeletedNodesQuery(
            after=page.cursor,
            limit=page.limit,
            sort=page.first_sort,
            order=page.first_order,
            then_by=page.then_by,
            q=page.q,
        ),
        actor,
    )
    set_page_headers(request, response, result)
    return [DeletedNodeResponse.from_domain(n) for n in result.items]


@router.get(
    "/random",
    response_model=NodeResponse,
    operation_id="get_random_node",
    responses=error_response(NodeNotFoundError, detail="No item matches"),
)
async def get_random_node(
    use_case: Annotated[RandomNode, Depends(get_random_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    filters: NodeFiltersDep,
) -> NodeResponse:
    """Fetch one of your items at random, for a "surprise me" button.

    Takes the same `type`, `favourite` and `collection` filters as `GET /node`
    and picks from what they match; `q` is ignored. 404 when nothing matches.
    """
    picked = await use_case.handle(
        ListNodesQuery(
            type=filters.type,
            favourite=filters.favourite,
            collection=filters.collection,
        ),
        actor,
    )
    return NodeResponse.from_domain(
        picked.node, cover_thumbnail_url=picked.cover_thumbnail_url
    )


@router.get(
    "/count",
    response_model=NodeCountResponse,
    operation_id="count_nodes",
    responses=error_response(
        CollectionNotFoundError,
        detail="Collection 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
    ),
)
async def count_nodes(
    use_case: Annotated[CountNodes, Depends(get_count_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    filters: NodeFiltersDep,
) -> NodeCountResponse:
    """Count the items `GET /node` would list for the same filters, with no cap.

    `Total-Count` on a search stops at 1000; this does not, so it can be slow
    for a very common search term.
    """
    count = await use_case.handle(
        ListNodesQuery(
            type=filters.type,
            q=filters.q,
            favourite=filters.favourite,
            collection=filters.collection,
        ),
        actor,
    )
    return NodeCountResponse(count=count)


@router.get(
    "/count/types",
    response_model=list[NodeTypeCountResponse],
    operation_id="count_node_types",
    responses=error_response(
        CollectionNotFoundError,
        detail="Collection 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
    ),
)
async def count_node_types(
    use_case: Annotated[CountNodeTypes, Depends(get_count_node_types_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    collection: Annotated[
        uuid.UUID | None,
        Query(
            description=(
                "Count only the items on this collection. For a smart "
                + "collection, the items matching its definition."
            )
        ),
    ] = None,
) -> list[NodeTypeCountResponse]:
    """Count your items per item type, biggest first.

    Only item types that have at least one of your items appear, so the shared
    list of item types never inflates the numbers. Items with no type are one
    row whose `type` is null. Counts are exact. With `collection`, only that
    collection's items count, so the rows match what `GET /node` lists for it.
    """
    rows = await use_case.handle(CountNodeTypesQuery(collection=collection), actor)
    return [NodeTypeCountResponse.from_domain(row) for row in rows]


@router.get(
    "/{node_id}",
    response_model=NodeResponse,
    operation_id="get_node",
    responses={
        **conditional_get_responses(),
        **error_response(
            NodeNotFoundError,
            detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
    },
)
async def get_node(
    node_id: NodeId,
    use_case: Annotated[GetNode, Depends(get_get_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalGetDep,
) -> NodeResponse | Response:
    """Fetch a single node by id."""
    node = await use_case.handle(GetNodeQuery(node_id=node_id), actor)
    # The body depends on the viewer's favourite, which `updated_at` does not track,
    # so only the ETag can say a cached copy is current.
    if earlier := cond.check_get(
        node, _viewer_state(node.favourite), honour_if_modified_since=False
    ):
        return earlier
    return NodeResponse.from_domain(node)


@router.get(
    "/{node_id}/contents",
    response_model=list[NodeContentsEntryResponse],
    operation_id="list_node_contents",
    responses={
        "200": {
            "headers": {
                "Link": {
                    "description": "RFC 8288 next-page cursor. Absent on last page.",
                    "schema": {"type": "string"},
                }
            }
        },
        **error_response(
            NodeNotFoundError,
            detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
        **error_response(
            EdgeTypeNotFoundError,
            detail="Relationship 'contains' not found",
        ),
        **error_response(
            ReachTooLargeError,
            detail="This reaches too many items to follow. Try fewer steps.",
        ),
        **error_response(
            RelationshipHoldsNothingError,
            detail="'sibling' does not hold items, so it has no contents or path",
        ),
        **error_response(
            InvalidReachDepthError, detail="Depth must be between 1 and 25"
        ),
    },
)
async def list_node_contents(
    node_id: NodeId,
    use_case: Annotated[ListItemContents, Depends(get_list_item_contents_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    relationship: Annotated[
        str,
        Query(description="Slug of the relationship to follow, such as `contains`."),
    ],
    depth: Annotated[
        int, Query(description="How many steps to follow, from 1 to 25.")
    ] = 1,
    after: PageAfter = None,
    limit: PageLimit = 50,
) -> list[NodeContentsEntryResponse]:
    """List the items this item holds, nearest first.

    Follows the relationship from the item to what it holds, then what those hold,
    up to `depth` steps. Each item appears once, at its nearest depth, ordered by
    depth and then id. Page with `after`, the id of the last item on the previous
    page.
    """
    found = await use_case.handle(
        ListItemContentsQuery(
            item_id=node_id,
            relationship=relationship,
            depth=depth,
            after=after,
            limit=limit + 1,
        ),
        actor,
    )
    if len(found) > limit:
        response.headers["Link"] = link_next_header(
            request, str(found[limit - 1].node.id)
        )
    return [
        NodeContentsEntryResponse(
            item=NodeResponse.from_domain(entry.node), depth=entry.depth
        )
        for entry in found[:limit]
    ]


@router.get(
    "/{node_id}/path",
    response_model=list[NodeResponse],
    operation_id="list_node_path",
    responses={
        **error_response(
            NodeNotFoundError,
            detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
        **error_response(
            EdgeTypeNotFoundError,
            detail="Relationship 'contains' not found",
        ),
        **error_response(
            ReachTooLargeError,
            detail="This reaches too many items to follow. Try fewer steps.",
        ),
        **error_response(
            RelationshipHoldsNothingError,
            detail="'sibling' does not hold items, so it has no contents or path",
        ),
        **error_response(
            InvalidReachDepthError, detail="Depth must be between 1 and 25"
        ),
    },
)
async def list_node_path(
    node_id: NodeId,
    use_case: Annotated[GetItemPath, Depends(get_get_item_path_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    relationship: Annotated[
        str,
        Query(description="Slug of the relationship to follow, such as `contains`."),
    ],
    depth: Annotated[
        int, Query(description="How many steps up to follow, from 1 to 25.")
    ] = 25,
) -> list[NodeResponse]:
    """List the items that hold this item, outermost first.

    The last entry is the item's direct holder. An item held in two places lists
    both holders at that distance, in id order.
    """
    holders = await use_case.handle(
        GetItemPathQuery(item_id=node_id, relationship=relationship, depth=depth),
        actor,
    )
    return [NodeResponse.from_domain(node) for node in holders]


@router.get(
    "",
    response_model=list[NodeResponse],
    operation_id="list_nodes",
    responses={
        **_TOTAL_COUNT_HEADERS,
        **error_response(
            CollectionNotFoundError,
            detail="Collection 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
    },
)
async def list_nodes(
    use_case: Annotated[ListNodes, Depends(get_list_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    filters: NodeFiltersDep,
    page: Annotated[PageParams[NodeSort], Query()],
    ids: Annotated[
        list[uuid.UUID] | None,
        Query(
            alias="id",
            max_length=MAX_IDS,
            description=(
                "Keep only the items with these ids, given once for each. Up to "
                + f"{MAX_IDS}. An id that is not an item you can see is left out. "
                + "Not allowed with a smart collection."
            ),
        ),
    ] = None,
) -> list[NodeResponse]:
    """List items, by id unless sorted.

    A smart collection sorts by `name`, `created_at` or `updated_at`; sorting it
    newest first needs a `sort` to go with `order=desc`.
    """
    result = await use_case.handle(
        ListNodesQuery(
            after=page.cursor,
            limit=page.limit,
            sort=page.first_sort,
            order=page.first_order,
            then_by=page.then_by,
            type=filters.type,
            q=filters.q,
            favourite=filters.favourite,
            collection=filters.collection,
            ids=None if ids is None else frozenset(ids),
        ),
        actor,
    )
    set_next_link(request, response, result.next)
    response.headers["Total-Count"] = str(result.total)
    if result.total_capped:
        response.headers["Total-Count-Capped"] = "true"

    return [
        NodeResponse.from_domain(node, cover_thumbnail_url=result.covers.get(node.id))
        for node in result.items
    ]


@router.patch(
    "/{node_id}",
    response_model=NodeResponse,
    operation_id="update_node",
    responses={
        **conditional_patch_responses(),
        **error_response(
            NodeNotFoundError,
            detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
        **error_response(ValidationError, detail="name must be provided"),
    },
)
async def update_node(
    node_id: NodeId,
    payload: UpdateNodeRequest,
    get_usecase: Annotated[GetNode, Depends(get_get_node_use_case)],
    update_usecase: Annotated[UpdateNode, Depends(get_update_node_use_case)],
    cond: ConditionalPatchDep,
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse | Response:
    """Update a node's editable fields."""
    current = await get_usecase.handle(GetNodeQuery(node_id=node_id), actor)
    if earlier := cond.check_patch(current, _viewer_state(current.favourite)):
        return earlier
    node = await update_usecase.handle(payload.to_command(node_id), actor)
    cond.set_response_etag(node, _viewer_state(node.favourite))
    return NodeResponse.from_domain(node)


@router.post(
    "/{node_id}/attributes/{key}/promote",
    response_model=NodeResponse,
    operation_id="promote_extra_schema_field",
    responses={
        **error_response(
            NodeNotFoundError,
            detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(
            InvalidSchemaError, detail="'condition' already exists on this item type"
        ),
    },
)
async def promote_extra_schema_field(
    node_id: NodeId,
    key: FieldKey,
    payload: PromoteExtraSchemaFieldRequest,
    use_case: Annotated[
        PromoteExtraSchemaField, Depends(get_promote_extra_schema_field_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse:
    """Make one of this item's own fields a field of its item type.

    This item's definition is used, and every other item of the type that has the
    field loses its own copy too, as `POST /nodes/fields/{key}/promote` does.
    Values are unchanged.
    """
    promoted = await use_case.handle(
        PromoteExtraSchemaFieldCommand(
            node_id=node_id, node_type_id=payload.node_type_id, key=key
        ),
        actor,
    )
    if promoted.node is None:
        raise NodeNotFoundError(f"Node {node_id} not found")
    return NodeResponse.from_domain(promoted.node)


@router.post(
    "/delete",
    status_code=204,
    operation_id="delete_nodes",
    responses=error_response(
        ValidationError,
        detail="Unknown or deleted items: 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
    ),
)
async def delete_nodes(
    payload: DeleteNodesRequest,
    use_case: Annotated[DeleteNodes, Depends(get_delete_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete several items at once, all or none.

    At most 200 ids. If any id is unknown or already deleted, nothing is deleted and
    the response names them. An item you can see but may not delete is a 403, which
    also deletes nothing.
    """
    await use_case.handle(payload.to_command(), actor)


@router.post(
    "/tags",
    response_model=TagNodesResponse,
    operation_id="tag_nodes",
    responses=error_response(
        ValidationError,
        detail="Unknown or deleted items: 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
    ),
)
async def tag_nodes(
    payload: TagNodesRequest,
    use_case: Annotated[TagNodes, Depends(get_tag_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> TagNodesResponse:
    """Add and remove tags on several items at once, all or none.

    At most 200 ids. Tags are trimmed and lowercased like any other tag. If any
    id is unknown or deleted, nothing changes.
    """
    changed = await use_case.handle(payload.to_command(), actor)
    return TagNodesResponse(changed=changed)


@router.delete(
    "/{node_id}",
    status_code=204,
    operation_id="delete_node",
    responses=error_response(
        NodeNotFoundError,
        detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
    ),
)
async def delete_node(
    node_id: NodeId,
    use_case: Annotated[DeleteNode, Depends(get_delete_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete a node."""
    await use_case.handle(DeleteNodeCommand(node_id=node_id), actor)


@router.post(
    "/{node_id}/restore",
    response_model=NodeResponse,
    operation_id="restore_node",
    responses={
        **error_response(
            NodeNotFoundError,
            detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
        **error_response(
            NodeTypeDeletedError,
            detail=(
                "The item type 'film' has been deleted. "
                + "Create an item type with that slug, then try again."
            ),
        ),
    },
)
async def restore_node(
    node_id: NodeId,
    use_case: Annotated[RestoreNode, Depends(get_restore_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse:
    """Bring a deleted item back.

    Its connections and collections come back with it; a connection that was
    deleted on its own stays deleted. If its item type has been deleted since,
    this is a 409 until a type with that slug exists again.
    """
    node = await use_case.handle(RestoreNodeCommand(node_id=node_id), actor)
    return NodeResponse.from_domain(node)


@router.post(
    "/{node_id}/duplicate",
    response_model=NodeResponse,
    status_code=201,
    operation_id="duplicate_node",
    responses=error_response(
        NodeNotFoundError,
        detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
    ),
)
async def duplicate_node(
    node_id: NodeId,
    payload: DuplicateNodeRequest,
    use_case: Annotated[DuplicateNode, Depends(get_duplicate_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse:
    """Copy an item under a new name.

    The copy has the original's type, description, fields and tags, its own id and
    history, and is not a favourite. Each flag adds one more thing from the
    original: connections, media (every attachment but the cover), the cover, and
    its manual collections. Media files are copied, so the two items are independent.
    """
    node = await use_case.handle(payload.to_command(node_id), actor)
    return NodeResponse.from_domain(node)


@router.delete(
    "/{node_id}/purge",
    status_code=204,
    operation_id="purge_node",
    responses=error_response(
        NodeNotFoundError,
        detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
    ),
)
async def purge_node(
    node_id: NodeId,
    use_case: Annotated[PurgeDeletedNode, Depends(get_purge_deleted_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Permanently delete an item that is in your deleted items. This cannot be undone.

    Its connections, collection memberships and attachments go with it, and so
    do media files only it used. An item that is not deleted is a 404. Needs a
    signed-in session: a personal access token cannot purge.
    """
    await use_case.handle(PurgeDeletedNodeCommand(node_id=node_id), actor)
