import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.conditional_request import ConditionalRequestDep
from app.entrypoints.api.shared.http.http_headers import (
    conditional_get_responses,
    conditional_patch_responses,
    link_next_header,
)
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.graph.adapters.api.dependencies import (
    get_count_nodes_use_case,
    get_create_node_use_case,
    get_delete_node_use_case,
    get_get_node_use_case,
    get_list_deleted_nodes_use_case,
    get_list_item_fields_use_case,
    get_list_nodes_use_case,
    get_promote_extra_schema_field_use_case,
    get_purge_deleted_node_use_case,
    get_restore_node_use_case,
    get_search_nodes_use_case,
    get_update_node_use_case,
)
from app.modules.graph.adapters.api.node.schemas import (
    CreateNodeRequest,
    DeletedNodeResponse,
    ItemFieldResponse,
    NodeCountResponse,
    NodeResponse,
    NodeSearchRequest,
    NodeSearchResponse,
    PromoteExtraSchemaFieldRequest,
    UpdateNodeRequest,
)
from app.modules.graph.application.count_nodes import CountNodes
from app.modules.graph.application.create_node import CreateNode
from app.modules.graph.application.delete_node import DeleteNode, DeleteNodeCommand
from app.modules.graph.application.get_node import GetNode, GetNodeQuery
from app.modules.graph.application.list_deleted_nodes import (
    ListDeletedNodes,
    ListDeletedNodesQuery,
)
from app.modules.graph.application.list_item_fields import (
    ListItemFields,
    ListItemFieldsQuery,
)
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.application.promote_extra_schema_field import (
    PromoteExtraSchemaField,
    PromoteExtraSchemaFieldCommand,
)
from app.modules.graph.application.purge_deleted_node import (
    PurgeDeletedNode,
    PurgeDeletedNodeCommand,
)
from app.modules.graph.application.restore_node import RestoreNode, RestoreNodeCommand
from app.modules.graph.application.search_nodes import SearchNodes, SearchNodesQuery
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.domain.errors import (
    CollectionNotFoundError,
    InvalidSchemaError,
    NodeNotFoundError,
    NodeTypeDeletedError,
    NodeTypeNotFoundError,
)
from app.modules.graph.domain.query import InvalidQueryError
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ValidationError

router = APIRouter(prefix="/node", tags=["Nodes"], route_class=PermissionAwareRoute)

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

_Q_DESCRIPTION = "Search text, matched case-insensitively."
_Q_DESCRIPTION += " Looks in the name, the description and every text or number"
_Q_DESCRIPTION += " value in the item's details. Field names, yes/no values, ratings,"
_Q_DESCRIPTION += " removed fields and fields excluded from search are not searched."


@dataclass
class NodeFilters:
    """Query parameters that choose which items a list or count covers."""

    type: str | None = None
    q: Annotated[str | None, Query(description=_Q_DESCRIPTION)] = None
    favourite: bool | None = None
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
    responses=error_response(
        InvalidQueryError, detail="where.children[0]: Unknown condition kind."
    ),
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


@router.get(
    "/item-fields",
    response_model=list[ItemFieldResponse],
    operation_id="list_item_fields",
)
async def list_item_fields(
    use_case: Annotated[ListItemFields, Depends(get_list_item_fields_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[ItemFieldResponse]:
    """List the fields your items carry themselves, most used first.

    These are the per-item fields a search can filter on. A field appears once
    per name and kind, with how many of your items declare it. Removed fields
    and fields without a recorded kind are left out. At most 200 are returned.
    """
    fields = await use_case.handle(ListItemFieldsQuery(), actor)
    return [ItemFieldResponse.from_domain(field) for field in fields]


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
    after: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[DeletedNodeResponse]:
    """List your deleted items, newest deleted first.

    `after` is the id of the last row of the previous page (the `Link` header
    carries it). An id that has since been restored or purged gives an empty page.
    """
    result = await use_case.handle(
        ListDeletedNodesQuery(after=after, limit=limit + 1), actor
    )
    if len(result.items) > limit:
        response.headers["Link"] = link_next_header(
            request, str(result.items[limit - 1].id)
        )
    response.headers["Total-Count"] = str(result.total)
    return [DeletedNodeResponse.from_domain(n) for n in result.items[:limit]]


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
    node_id: uuid.UUID,
    use_case: Annotated[GetNode, Depends(get_get_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalRequestDep,
) -> NodeResponse | Response:
    """Fetch a single node by id."""
    node = await use_case.handle(GetNodeQuery(node_id=node_id), actor)
    if earlier := cond.check_get(node):
        return earlier
    return NodeResponse.from_domain(node)


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
    after: uuid.UUID | None = None,
    limit: int = 50,
) -> list[NodeResponse]:
    """List node, paginated by id."""
    result = await use_case.handle(
        ListNodesQuery(
            after=after,
            limit=limit + 1,
            type=filters.type,
            q=filters.q,
            favourite=filters.favourite,
            collection=filters.collection,
        ),
        actor,
    )
    if len(result.items) > limit:
        response.headers["Link"] = link_next_header(
            request, str(result.items[limit - 1].id)
        )
    response.headers["Total-Count"] = str(result.total)
    if result.total_capped:
        response.headers["Total-Count-Capped"] = "true"

    return [NodeResponse.from_domain(node) for node in result.items[:limit]]


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
    node_id: uuid.UUID,
    payload: UpdateNodeRequest,
    get_usecase: Annotated[GetNode, Depends(get_get_node_use_case)],
    update_usecase: Annotated[UpdateNode, Depends(get_update_node_use_case)],
    cond: ConditionalRequestDep,
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse | Response:
    """Update a node's editable fields."""
    current = await get_usecase.handle(GetNodeQuery(node_id=node_id), actor)
    if earlier := cond.check_patch(current):
        return earlier
    node = await update_usecase.handle(payload.to_command(node_id), actor)
    cond.set_response_etag(node)
    return NodeResponse.from_domain(node)


@router.post(
    "/{node_id}/attribute/{key}/promote",
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
    node_id: uuid.UUID,
    key: str,
    payload: PromoteExtraSchemaFieldRequest,
    use_case: Annotated[
        PromoteExtraSchemaField, Depends(get_promote_extra_schema_field_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse:
    """Move an overlay field's definition onto the item type; the value is unchanged."""
    node = await use_case.handle(
        PromoteExtraSchemaFieldCommand(
            node_id=node_id, node_type_id=payload.node_type_id, key=key
        ),
        actor,
    )
    return NodeResponse.from_domain(node)


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
    node_id: uuid.UUID,
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
    node_id: uuid.UUID,
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
    node_id: uuid.UUID,
    use_case: Annotated[PurgeDeletedNode, Depends(get_purge_deleted_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Permanently delete an item that is in your deleted items. This cannot be undone.

    Its connections, collection memberships and attachments go with it, and so
    do media files only it used. An item that is not deleted is a 404. Needs a
    signed-in session: a personal access token cannot purge.
    """
    await use_case.handle(PurgeDeletedNodeCommand(node_id=node_id), actor)
