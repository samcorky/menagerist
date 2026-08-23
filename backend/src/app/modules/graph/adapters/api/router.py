import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.graph.adapters.api.dependencies import (
    get_create_node_use_case,
    get_get_node_use_case,
    get_list_nodes_use_case,
)
from app.modules.graph.adapters.api.schemas import (
    CreateNodeRequest,
    ListNodesResponse,
    NodeResponse,
)
from app.modules.graph.application.create_node import CreateNode
from app.modules.graph.application.get_node import GetNode, GetNodeQuery
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.domain.errors import NodeNotFoundError
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ValidationError

router = APIRouter(prefix="/nodes", tags=["Nodes"])


@router.post(
    "",
    response_model=NodeResponse,
    status_code=201,
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
    responses=error_response(
        NodeNotFoundError,
        detail="Node 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10 not found",
    ),
)
async def get_node(
    node_id: uuid.UUID,
    use_case: Annotated[GetNode, Depends(get_get_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse:
    """Fetch a single node by id."""
    node = await use_case.handle(GetNodeQuery(node_id=node_id), actor)
    return NodeResponse.from_domain(node)


@router.get("", response_model=ListNodesResponse)
async def list_nodes(
    use_case: Annotated[ListNodes, Depends(get_list_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    after: uuid.UUID | None = None,
    limit: int = 50,
) -> ListNodesResponse:
    """List nodes, paginated by id."""
    nodes = await use_case.handle(ListNodesQuery(after=after, limit=limit), actor)
    return ListNodesResponse(items=[NodeResponse.from_domain(node) for node in nodes])
