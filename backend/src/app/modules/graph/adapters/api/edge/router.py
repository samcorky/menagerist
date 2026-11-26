import uuid
from typing import Annotated

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
    link_header_responses,
    link_next_header,
)
from app.entrypoints.api.shared.http.parameters import EdgeId, PageParams
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.graph.adapters.api.dependencies import (
    get_create_edge_use_case,
    get_create_edges_use_case,
    get_delete_edge_use_case,
    get_get_edge_use_case,
    get_list_edges_use_case,
    get_update_edge_use_case,
)
from app.modules.graph.adapters.api.edge.schemas import (
    CreateEdgeRequest,
    CreateEdgesRequest,
    CreateEdgesResponse,
    EdgeResponse,
    UpdateEdgeRequest,
)
from app.modules.graph.application.create_edge import CreateEdge
from app.modules.graph.application.create_edges import CreateEdges
from app.modules.graph.application.delete_edge import DeleteEdge, DeleteEdgeCommand
from app.modules.graph.application.get_edge import GetEdge, GetEdgeQuery
from app.modules.graph.application.list_edges import EdgeSort, ListEdges, ListEdgesQuery
from app.modules.graph.application.update_edge import UpdateEdge
from app.modules.graph.domain.errors import EdgeNotFoundError, NodeNotFoundError
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.paging import decode_cursor

router = APIRouter(prefix="/edges", tags=["Edges"], route_class=PermissionAwareRoute)


@router.post(
    "",
    response_model=EdgeResponse,
    status_code=201,
    operation_id="create_edge",
    responses={
        **error_response(ValidationError, detail="type must be provided"),
        **error_response(
            NodeNotFoundError,
            detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
    },
)
async def create_edge(
    payload: CreateEdgeRequest,
    use_case: Annotated[CreateEdge, Depends(get_create_edge_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> EdgeResponse:
    """Create a new edge between two existing node."""
    edge = await use_case.handle(payload.to_command(), actor)
    return EdgeResponse.from_domain(edge)


@router.post(
    "/batch",
    response_model=CreateEdgesResponse,
    status_code=201,
    operation_id="create_edges",
    responses={
        **error_response(ValidationError, detail="type must be provided"),
        **error_response(
            NodeNotFoundError,
            detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
        ),
    },
)
async def create_edges(
    payload: CreateEdgesRequest,
    use_case: Annotated[CreateEdges, Depends(get_create_edges_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> CreateEdgesResponse:
    """Connect one source to several targets at once, skipping existing connections.

    With `reverse`, each target connects to the source instead, so many items can
    be connected to one. Either way, the source appearing among the targets is a
    400: an item cannot be connected to itself.
    """
    result = await use_case.handle(payload.to_command(), actor)
    return CreateEdgesResponse(
        created=[EdgeResponse.from_domain(edge) for edge in result.created],
        skipped=result.skipped,
    )


@router.get(
    "/{edge_id}",
    response_model=EdgeResponse,
    operation_id="get_edge",
    responses={
        **conditional_get_responses(),
        **error_response(
            EdgeNotFoundError,
            detail="Edge 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e11 not found",
        ),
    },
)
async def get_edge(
    edge_id: EdgeId,
    use_case: Annotated[GetEdge, Depends(get_get_edge_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalGetDep,
) -> EdgeResponse | Response:
    """Fetch a single edge by id."""
    edge = await use_case.handle(GetEdgeQuery(edge_id=edge_id), actor)
    if earlier := cond.check_get(edge):
        return earlier
    return EdgeResponse.from_domain(edge)


@router.get(
    "",
    response_model=list[EdgeResponse],
    operation_id="list_edges",
    responses={**link_header_responses()},
)
async def list_edges(
    use_case: Annotated[ListEdges, Depends(get_list_edges_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    page: Annotated[PageParams[EdgeSort], Query()],
    node_id: Annotated[
        uuid.UUID | None,
        Query(description="Keep connections to or from the item with this id."),
    ] = None,
) -> list[EdgeResponse]:
    """List edges, by id unless sorted, optionally those of one item."""
    result = await use_case.handle(
        ListEdgesQuery(
            after=None if page.after is None else decode_cursor(page.after),
            limit=page.limit,
            sort=page.sort,
            order=page.order,
            node_id=node_id,
        ),
        actor,
    )
    if result.next is not None:
        response.headers["Link"] = link_next_header(request, result.next.encode())
    return [EdgeResponse.from_domain(edge) for edge in result.items]


@router.patch(
    "/{edge_id}",
    response_model=EdgeResponse,
    operation_id="update_edge",
    responses={
        **conditional_patch_responses(),
        **error_response(
            EdgeNotFoundError,
            detail="Edge 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e11 not found",
        ),
    },
)
async def update_edge(
    edge_id: EdgeId,
    payload: UpdateEdgeRequest,
    update_use_case: Annotated[UpdateEdge, Depends(get_update_edge_use_case)],
    get_use_case: Annotated[GetEdge, Depends(get_get_edge_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalPatchDep,
) -> EdgeResponse | Response:
    """Update an edge's editable fields."""
    current = await get_use_case.handle(GetEdgeQuery(edge_id=edge_id), actor)
    if earlier := cond.check_patch(current):
        return earlier
    edge = await update_use_case.handle(payload.to_command(edge_id), actor)
    cond.set_response_etag(edge)
    return EdgeResponse.from_domain(edge)


@router.delete(
    "/{edge_id}",
    status_code=204,
    operation_id="delete_edge",
    responses=error_response(
        EdgeNotFoundError,
        detail="Edge 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e11 not found",
    ),
)
async def delete_edge(
    edge_id: EdgeId,
    use_case: Annotated[DeleteEdge, Depends(get_delete_edge_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete an edge."""
    await use_case.handle(DeleteEdgeCommand(edge_id=edge_id), actor)
