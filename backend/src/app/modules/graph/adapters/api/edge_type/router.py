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
    get_create_edge_type_use_case,
    get_delete_edge_type_use_case,
    get_get_edge_type_use_case,
    get_list_edge_types_use_case,
    get_update_edge_type_use_case,
)
from app.modules.graph.adapters.api.edge_type.schemas import (
    CreateEdgeTypeRequest,
    EdgeTypeResponse,
    UpdateEdgeTypeRequest,
)
from app.modules.graph.application.create_edge_type import CreateEdgeType
from app.modules.graph.application.delete_edge_type import (
    DeleteEdgeType,
    DeleteEdgeTypeCommand,
)
from app.modules.graph.application.get_edge_type import GetEdgeType, GetEdgeTypeQuery
from app.modules.graph.application.list_edge_types import (
    ListEdgeTypes,
    ListEdgeTypesQuery,
)
from app.modules.graph.application.update_edge_type import UpdateEdgeType
from app.modules.graph.domain.errors import (
    EdgeTypeNotFoundError,
    EdgeTypeSlugConflictError,
)
from app.shared_kernel.actor import Actor

router = APIRouter(prefix="/edge-type", tags=["Edge Types"])


@router.post(
    "",
    response_model=EdgeTypeResponse,
    status_code=201,
    operation_id="create_edge_type",
    responses=error_response(
        EdgeTypeSlugConflictError,
        detail="EdgeType with slug 'directed-by' already exists",
    ),
)
async def create_edge_type(
    payload: CreateEdgeTypeRequest,
    use_case: Annotated[CreateEdgeType, Depends(get_create_edge_type_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> EdgeTypeResponse:
    """Create a new edge type."""
    edge_type = await use_case.handle(payload.to_command(), actor)
    return EdgeTypeResponse.from_domain(edge_type)


@router.get(
    "/{edge_type_id}",
    response_model=EdgeTypeResponse,
    operation_id="get_edge_type",
    responses={
        **conditional_get_responses(),
        **error_response(
            EdgeTypeNotFoundError,
            detail="EdgeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
    },
)
async def get_edge_type(
    edge_type_id: uuid.UUID,
    use_case: Annotated[GetEdgeType, Depends(get_get_edge_type_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalRequestDep,
) -> EdgeTypeResponse | Response:
    """Fetch a single edge type by id."""
    edge_type = await use_case.handle(
        GetEdgeTypeQuery(edge_type_id=edge_type_id), actor
    )
    if earlier := cond.check_get(edge_type):
        return earlier
    return EdgeTypeResponse.from_domain(edge_type)


@router.get(
    "",
    response_model=list[EdgeTypeResponse],
    operation_id="list_edge_types",
    responses={**link_header_responses()},
)
async def list_edge_types(
    use_case: Annotated[ListEdgeTypes, Depends(get_list_edge_types_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    after: uuid.UUID | None = None,
    limit: int = 50,
) -> list[EdgeTypeResponse]:
    """List edge types, paginated by id."""
    edge_types = await use_case.handle(
        ListEdgeTypesQuery(after=after, limit=limit + 1), actor
    )
    if len(edge_types) > limit:
        response.headers["Link"] = link_next_header(
            request, str(edge_types[limit - 1].id)
        )

    return [EdgeTypeResponse.from_domain(et) for et in edge_types[:limit]]


@router.patch(
    "/{edge_type_id}",
    response_model=EdgeTypeResponse,
    operation_id="update_edge_type",
    responses={
        **conditional_patch_responses(),
        **error_response(
            EdgeTypeNotFoundError,
            detail="EdgeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
    },
)
async def update_edge_type(
    edge_type_id: uuid.UUID,
    payload: UpdateEdgeTypeRequest,
    get_usecase: Annotated[GetEdgeType, Depends(get_get_edge_type_use_case)],
    update_usecase: Annotated[UpdateEdgeType, Depends(get_update_edge_type_use_case)],
    cond: ConditionalRequestDep,
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> EdgeTypeResponse | Response:
    """Update an edge type's editable fields. `slug` is immutable."""
    current = await get_usecase.handle(
        GetEdgeTypeQuery(edge_type_id=edge_type_id), actor
    )
    if earlier := cond.check_patch(current):
        return earlier
    edge_type = await update_usecase.handle(payload.to_command(edge_type_id), actor)
    cond.set_response_etag(edge_type)
    return EdgeTypeResponse.from_domain(edge_type)


@router.delete(
    "/{edge_type_id}",
    status_code=204,
    operation_id="delete_edge_type",
    responses=error_response(
        EdgeTypeNotFoundError,
        detail="EdgeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
    ),
)
async def delete_edge_type(
    edge_type_id: uuid.UUID,
    use_case: Annotated[DeleteEdgeType, Depends(get_delete_edge_type_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete an edge type."""
    await use_case.handle(DeleteEdgeTypeCommand(edge_type_id=edge_type_id), actor)
