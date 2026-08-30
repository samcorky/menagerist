import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.conditional_request import ConditionalRequestDep
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http_headers import (
    conditional_get_responses,
    conditional_patch_responses,
    link_header_responses,
    link_next_header,
)
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.graph.adapters.api.dependencies import (
    get_create_edge_use_case,
    get_delete_edge_use_case,
    get_get_edge_use_case,
    get_list_edges_use_case,
    get_update_edge_use_case,
)
from app.modules.graph.adapters.api.edge.schemas import (
    CreateEdgeRequest,
    EdgeResponse,
    UpdateEdgeRequest,
)
from app.modules.graph.application.create_edge import CreateEdge
from app.modules.graph.application.delete_edge import DeleteEdge, DeleteEdgeCommand
from app.modules.graph.application.get_edge import GetEdge, GetEdgeQuery
from app.modules.graph.application.list_edges import ListEdges, ListEdgesQuery
from app.modules.graph.application.update_edge import UpdateEdge
from app.modules.graph.domain.errors import EdgeNotFoundError, NodeNotFoundError
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ValidationError

router = APIRouter(prefix="/edge", tags=["Edges"])


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
    edge_id: uuid.UUID,
    use_case: Annotated[GetEdge, Depends(get_get_edge_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalRequestDep,
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
    after: uuid.UUID | None = None,
    limit: int = 50,
    node_id: uuid.UUID | None = None,
) -> list[EdgeResponse]:
    """List edge, paginated by id and optionally filtered to one node."""
    edges = await use_case.handle(
        ListEdgesQuery(after=after, limit=limit + 1, node_id=node_id), actor
    )
    if len(edges) > limit:
        response.headers["Link"] = link_next_header(request, str(edges[limit - 1].id))
    return [EdgeResponse.from_domain(edge) for edge in edges[:limit]]


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
    edge_id: uuid.UUID,
    payload: UpdateEdgeRequest,
    update_use_case: Annotated[UpdateEdge, Depends(get_update_edge_use_case)],
    get_use_case: Annotated[GetEdge, Depends(get_get_edge_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalRequestDep,
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
    edge_id: uuid.UUID,
    use_case: Annotated[DeleteEdge, Depends(get_delete_edge_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete an edge."""
    await use_case.handle(DeleteEdgeCommand(edge_id=edge_id), actor)
