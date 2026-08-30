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
    get_create_node_type_use_case,
    get_delete_node_type_use_case,
    get_get_node_type_use_case,
    get_list_node_types_use_case,
    get_update_node_type_use_case,
)
from app.modules.graph.adapters.api.node_type.schemas import (
    CreateNodeTypeRequest,
    NodeTypeResponse,
    UpdateNodeTypeRequest,
)
from app.modules.graph.application.create_node_type import CreateNodeType
from app.modules.graph.application.delete_node_type import (
    DeleteNodeType,
    DeleteNodeTypeCommand,
)
from app.modules.graph.application.get_node_type import GetNodeType, GetNodeTypeQuery
from app.modules.graph.application.list_node_types import (
    ListNodeTypes,
    ListNodeTypesQuery,
)
from app.modules.graph.application.update_node_type import UpdateNodeType
from app.modules.graph.domain.errors import (
    NodeTypeNotFoundError,
    NodeTypeSlugConflictError,
)
from app.shared_kernel.actor import Actor

router = APIRouter(prefix="/node-type", tags=["Node Types"])


@router.post(
    "",
    response_model=NodeTypeResponse,
    status_code=201,
    operation_id="create_node_type",
    responses=error_response(
        NodeTypeSlugConflictError, detail="NodeType with slug 'film' already exists"
    ),
)
async def create_node_type(
    payload: CreateNodeTypeRequest,
    use_case: Annotated[CreateNodeType, Depends(get_create_node_type_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeTypeResponse:
    """Create a new node type."""
    node_type = await use_case.handle(payload.to_command(), actor)
    return NodeTypeResponse.from_domain(node_type)


@router.get(
    "/{node_type_id}",
    response_model=NodeTypeResponse,
    operation_id="get_node_type",
    responses={
        **conditional_get_responses(),
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
    },
)
async def get_node_type(
    node_type_id: uuid.UUID,
    use_case: Annotated[GetNodeType, Depends(get_get_node_type_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalRequestDep,
) -> NodeTypeResponse | Response:
    """Fetch a single node type by id."""
    node_type = await use_case.handle(
        GetNodeTypeQuery(node_type_id=node_type_id), actor
    )
    if earlier := cond.check_get(node_type):
        return earlier
    return NodeTypeResponse.from_domain(node_type)


@router.get(
    "",
    response_model=list[NodeTypeResponse],
    operation_id="list_node_types",
    responses={**link_header_responses()},
)
async def list_node_types(
    use_case: Annotated[ListNodeTypes, Depends(get_list_node_types_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    after: uuid.UUID | None = None,
    limit: int = 50,
) -> list[NodeTypeResponse]:
    """List node types, paginated by id."""
    node_types = await use_case.handle(
        ListNodeTypesQuery(after=after, limit=limit + 1), actor
    )
    if len(node_types) > limit:
        response.headers["Link"] = link_next_header(
            request, str(node_types[limit - 1].id)
        )

    return [NodeTypeResponse.from_domain(nt) for nt in node_types[:limit]]


@router.patch(
    "/{node_type_id}",
    response_model=NodeTypeResponse,
    operation_id="update_node_type",
    responses={
        **conditional_patch_responses(),
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
    },
)
async def update_node_type(
    node_type_id: uuid.UUID,
    payload: UpdateNodeTypeRequest,
    get_usecase: Annotated[GetNodeType, Depends(get_get_node_type_use_case)],
    update_usecase: Annotated[UpdateNodeType, Depends(get_update_node_type_use_case)],
    cond: ConditionalRequestDep,
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeTypeResponse | Response:
    """Update a node type's editable fields. `slug` is immutable."""
    current = await get_usecase.handle(
        GetNodeTypeQuery(node_type_id=node_type_id), actor
    )
    if earlier := cond.check_patch(current):
        return earlier
    node_type = await update_usecase.handle(payload.to_command(node_type_id), actor)
    cond.set_response_etag(node_type)
    return NodeTypeResponse.from_domain(node_type)


@router.delete(
    "/{node_type_id}",
    status_code=204,
    operation_id="delete_node_type",
    responses=error_response(
        NodeTypeNotFoundError,
        detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
    ),
)
async def delete_node_type(
    node_type_id: uuid.UUID,
    use_case: Annotated[DeleteNodeType, Depends(get_delete_node_type_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete a node type."""
    await use_case.handle(DeleteNodeTypeCommand(node_type_id=node_type_id), actor)
