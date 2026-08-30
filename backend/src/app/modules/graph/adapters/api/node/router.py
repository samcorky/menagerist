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
    get_create_node_use_case,
    get_delete_node_use_case,
    get_get_node_use_case,
    get_list_nodes_use_case,
    get_update_node_use_case,
)
from app.modules.graph.adapters.api.node.schemas import (
    CreateNodeRequest,
    NodeResponse,
    UpdateNodeRequest,
)
from app.modules.graph.application.create_node import CreateNode
from app.modules.graph.application.delete_node import DeleteNode, DeleteNodeCommand
from app.modules.graph.application.get_node import GetNode, GetNodeQuery
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.domain.errors import NodeNotFoundError
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ValidationError

router = APIRouter(prefix="/node", tags=["Nodes"])


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
    responses={**link_header_responses()},
)
async def list_nodes(
    use_case: Annotated[ListNodes, Depends(get_list_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    after: uuid.UUID | None = None,
    limit: int = 50,
    type: str | None = None,
) -> list[NodeResponse]:
    """List node, paginated by id."""
    nodes = await use_case.handle(
        ListNodesQuery(after=after, limit=limit + 1, type=type), actor
    )
    if len(nodes) > limit:
        response.headers["Link"] = link_next_header(request, str(nodes[limit - 1].id))

    return [NodeResponse.from_domain(node) for node in nodes[:limit]]


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
