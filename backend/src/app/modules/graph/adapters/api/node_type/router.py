from typing import TYPE_CHECKING, Annotated

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
from app.entrypoints.api.shared.http.parameters import (
    FieldKey,
    NodeTypeId,
    PageLimit,
    PageParams,
    SubFieldKey,
)
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.graph.adapters.api.attribute_schemas import AttributeUsageResponse
from app.modules.graph.adapters.api.dependencies import (
    get_count_node_type_attribute_usage_use_case,
    get_create_node_type_use_case,
    get_delete_node_type_use_case,
    get_get_node_type_use_case,
    get_list_attribute_values_use_case,
    get_list_node_types_use_case,
    get_list_shared_subtype_fields_use_case,
    get_list_subtypes_use_case,
    get_plan_parent_change_use_case,
    get_promote_subtype_field_use_case,
    get_purge_node_type_attribute_use_case,
    get_update_node_type_use_case,
)
from app.modules.graph.adapters.api.node_type.schemas import (
    AttributeValueCountResponse,
    CreateNodeTypeRequest,
    NodeTypeResponse,
    ParentChangePlanResponse,
    ParentChangeRequest,
    PromotedSubtypeFieldResponse,
    SharedSubtypeFieldResponse,
    UpdateNodeTypeRequest,
)
from app.modules.graph.application.count_node_type_attribute_usage import (
    CountNodeTypeAttributeUsage,
    CountNodeTypeAttributeUsageQuery,
)
from app.modules.graph.application.create_node_type import CreateNodeType
from app.modules.graph.application.delete_node_type import (
    DeleteNodeType,
    DeleteNodeTypeCommand,
)
from app.modules.graph.application.get_node_type import GetNodeType, GetNodeTypeQuery
from app.modules.graph.application.list_attribute_values import (
    ListAttributeValues,
    ListAttributeValuesQuery,
)
from app.modules.graph.application.list_node_types import (
    ListNodeTypes,
    ListNodeTypesQuery,
    NodeTypeSort,
)
from app.modules.graph.application.list_shared_subtype_fields import (
    ListSharedSubtypeFields,
    ListSharedSubtypeFieldsQuery,
)
from app.modules.graph.application.list_subtypes import ListSubtypes, ListSubtypesQuery
from app.modules.graph.application.plan_parent_change import PlanParentChange
from app.modules.graph.application.promote_subtype_field import (
    PromoteSubtypeField,
    PromoteSubtypeFieldCommand,
)
from app.modules.graph.application.purge_node_type_attribute import (
    PurgeNodeTypeAttribute,
    PurgeNodeTypeAttributeCommand,
)
from app.modules.graph.application.update_node_type import UpdateNodeType
from app.modules.graph.domain.errors import (
    InvalidParentTypeError,
    InvalidSchemaError,
    NodeTypeHasSubtypesError,
    NodeTypeNotFoundError,
    NodeTypeSlugConflictError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.paging import decode_cursor

if TYPE_CHECKING:
    from app.modules.graph.domain.node_type import NodeType

router = APIRouter(
    prefix="/node-types", tags=["Node Types"], route_class=PermissionAwareRoute
)


def _etag_extra(node_type: NodeType) -> str | None:
    """A subtype shows its parent's fields, so a change to the parent moves the tag."""
    changed = node_type.parent_updated_at
    return changed.isoformat() if changed is not None else None


@router.post(
    "",
    response_model=NodeTypeResponse,
    status_code=201,
    operation_id="create_node_type",
    responses={
        **error_response(
            NodeTypeSlugConflictError, detail="NodeType with slug 'film' already exists"
        ),
        **error_response(
            InvalidParentTypeError, detail="Parent type 'memorabilia' not found"
        ),
    },
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
    node_type_id: NodeTypeId,
    use_case: Annotated[GetNodeType, Depends(get_get_node_type_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalGetDep,
) -> NodeTypeResponse | Response:
    """Fetch a single node type by id."""
    node_type = await use_case.handle(
        GetNodeTypeQuery(node_type_id=node_type_id), actor
    )
    if earlier := cond.check_get(node_type, _etag_extra(node_type)):
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
    page: Annotated[PageParams[NodeTypeSort], Query()],
) -> list[NodeTypeResponse]:
    """List node types, by id unless sorted."""
    result = await use_case.handle(
        ListNodeTypesQuery(
            after=None if page.after is None else decode_cursor(page.after),
            limit=page.limit,
            sort=page.sort,
            order=page.order,
        ),
        actor,
    )
    if result.next is not None:
        response.headers["Link"] = link_next_header(request, result.next.encode())
    return [NodeTypeResponse.from_domain(nt) for nt in result.items]


@router.get(
    "/{node_type_id}/subtypes",
    response_model=list[NodeTypeResponse],
    operation_id="list_subtypes",
    responses={
        **link_header_responses(),
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
    },
)
async def list_subtypes(
    node_type_id: NodeTypeId,
    use_case: Annotated[ListSubtypes, Depends(get_list_subtypes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    page: Annotated[PageParams[NodeTypeSort], Query()],
) -> list[NodeTypeResponse]:
    """List the subtypes of an item type, by id unless sorted."""
    result = await use_case.handle(
        ListSubtypesQuery(
            node_type_id=node_type_id,
            after=None if page.after is None else decode_cursor(page.after),
            limit=page.limit,
            sort=page.sort,
            order=page.order,
        ),
        actor,
    )
    if result.next is not None:
        response.headers["Link"] = link_next_header(request, result.next.encode())
    return [NodeTypeResponse.from_domain(nt) for nt in result.items]


@router.get(
    "/{node_type_id}/subtypes/fields",
    response_model=list[SharedSubtypeFieldResponse],
    operation_id="list_shared_subtype_fields",
    responses=error_response(
        NodeTypeNotFoundError,
        detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
    ),
)
async def list_shared_subtype_fields(
    node_type_id: NodeTypeId,
    use_case: Annotated[
        ListSharedSubtypeFields, Depends(get_list_shared_subtype_fields_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[SharedSubtypeFieldResponse]:
    """List the fields several subtypes of an item type each define themselves.

    A field is listed when two or more subtypes define the same key as the same
    kind of field. These are the fields that could move up to the parent item type
    with the promote action. An item type with no subtypes lists none.
    """
    fields = await use_case.handle(
        ListSharedSubtypeFieldsQuery(node_type_id=node_type_id), actor
    )
    return [SharedSubtypeFieldResponse.from_domain(f) for f in fields]


@router.post(
    "/{node_type_id}/subtypes/fields/{key}/promote",
    response_model=PromotedSubtypeFieldResponse,
    operation_id="promote_subtype_field",
    responses={
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(
            InvalidSchemaError,
            detail="1 subtype keeps Condition as a different kind of field. "
            + "Change them to match first.",
        ),
    },
)
async def promote_subtype_field(
    node_type_id: NodeTypeId,
    key: FieldKey,
    use_case: Annotated[
        PromoteSubtypeField, Depends(get_promote_subtype_field_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> PromotedSubtypeFieldResponse:
    """Move a field the subtypes define up to their parent item type.

    Every subtype that defines the key loses its own copy, in one change, and its
    items keep their values. The definition most subtypes share is used, with the
    choices of all of them, and it is required if any subtype required it. Refused
    when some subtype keeps the key as another kind of field, or has it hidden.
    """
    promoted = await use_case.handle(
        PromoteSubtypeFieldCommand(node_type_id=node_type_id, key=key), actor
    )
    return PromotedSubtypeFieldResponse(
        subtypes=promoted.subtypes,
        node_type=NodeTypeResponse.from_domain(promoted.node_type),
    )


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
        **error_response(
            InvalidParentTypeError,
            detail="'poster' has fields its parent type 'memorabilia' already has: "
            + "condition",
        ),
    },
)
async def update_node_type(
    node_type_id: NodeTypeId,
    payload: UpdateNodeTypeRequest,
    get_usecase: Annotated[GetNodeType, Depends(get_get_node_type_use_case)],
    update_usecase: Annotated[UpdateNodeType, Depends(get_update_node_type_use_case)],
    cond: ConditionalPatchDep,
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeTypeResponse | Response:
    """Update a node type's editable fields. `slug` is immutable."""
    current = await get_usecase.handle(
        GetNodeTypeQuery(node_type_id=node_type_id), actor
    )
    if earlier := cond.check_patch(current, _etag_extra(current)):
        return earlier
    node_type = await update_usecase.handle(payload.to_command(node_type_id), actor)
    cond.set_response_etag(node_type, _etag_extra(node_type))
    return NodeTypeResponse.from_domain(node_type)


@router.post(
    "/{node_type_id}/parent/plan",
    response_model=ParentChangePlanResponse,
    operation_id="plan_parent_change",
    responses={
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(
            InvalidParentTypeError, detail="Parent type 'memorabilia' not found"
        ),
    },
)
async def plan_parent_change(
    node_type_id: NodeTypeId,
    payload: ParentChangeRequest,
    use_case: Annotated[PlanParentChange, Depends(get_plan_parent_change_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ParentChangePlanResponse:
    """Preview giving an item type another parent, or none, without changing it.

    Reports which fields would be merged, copied onto the type or archived, and
    whether the change is allowed as asked. Nothing is saved. A clash or a field
    defined as a different kind is reported with `allowed: false`, not as an error.
    """
    plan = await use_case.handle(payload.to_query(node_type_id), actor)
    return ParentChangePlanResponse.from_domain(plan)


@router.delete(
    "/{node_type_id}",
    status_code=204,
    operation_id="delete_node_type",
    responses={
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(
            NodeTypeHasSubtypesError,
            detail="Item type 'memorabilia' still has subtypes: poster, figure",
        ),
        **error_response(
            ForbiddenError, detail="You do not have permission to do this."
        ),
    },
)
async def delete_node_type(
    node_type_id: NodeTypeId,
    use_case: Annotated[DeleteNodeType, Depends(get_delete_node_type_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete a node type."""
    await use_case.handle(DeleteNodeTypeCommand(node_type_id=node_type_id), actor)


@router.get(
    "/{node_type_id}/attributes/{key}/usage",
    response_model=AttributeUsageResponse,
    operation_id="get_node_type_attribute_usage",
    responses=error_response(
        NodeTypeNotFoundError,
        detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
    ),
)
async def count_node_type_attribute_usage(
    node_type_id: NodeTypeId,
    key: FieldKey,
    use_case: Annotated[
        CountNodeTypeAttributeUsage,
        Depends(get_count_node_type_attribute_usage_use_case),
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
    value: Annotated[
        str | None,
        Query(description="Count only items where the field holds this value."),
    ] = None,
    sub_key: SubFieldKey = None,
) -> AttributeUsageResponse:
    """Count nodes of this type holding `key`, optionally where it equals `value`.

    With `sub_key`, `key` names a group (table) property and this counts nodes
    where any row of that array holds `sub_key`.
    """
    count = await use_case.handle(
        CountNodeTypeAttributeUsageQuery(
            node_type_id=node_type_id, key=key, sub_key=sub_key, value=value
        ),
        actor,
    )
    return AttributeUsageResponse(count=count)


@router.get(
    "/{node_type_id}/attributes/{key}/values",
    response_model=list[AttributeValueCountResponse],
    operation_id="list_attribute_values",
    responses=error_response(
        NodeTypeNotFoundError,
        detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
    ),
)
async def list_attribute_values(
    node_type_id: NodeTypeId,
    key: FieldKey,
    use_case: Annotated[
        ListAttributeValues, Depends(get_list_attribute_values_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
    q: Annotated[
        str | None,
        Query(description="Keep values containing this text, ignoring case."),
    ] = None,
    limit: PageLimit = 20,
) -> list[AttributeValueCountResponse]:
    """List previously-used string values of `key` on nodes of this type.

    Ordered most-used first, optionally filtered by a case-insensitive
    substring `q`.
    """
    values = await use_case.handle(
        ListAttributeValuesQuery(node_type_id=node_type_id, key=key, q=q, limit=limit),
        actor,
    )
    return [AttributeValueCountResponse(value=v.value, count=v.count) for v in values]


@router.delete(
    "/{node_type_id}/attributes/{key}",
    status_code=204,
    operation_id="purge_node_type_attribute",
    responses={
        **error_response(
            NodeTypeNotFoundError,
            detail="NodeType 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
        ),
        **error_response(
            ForbiddenError, detail="You do not have permission to do this."
        ),
    },
)
async def purge_node_type_attribute(
    node_type_id: NodeTypeId,
    key: FieldKey,
    use_case: Annotated[
        PurgeNodeTypeAttribute, Depends(get_purge_node_type_attribute_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
    sub_key: SubFieldKey = None,
) -> None:
    """Permanently remove `key` from every node of this type (cannot be undone).

    With `sub_key`, `key` names a group (table) property and only `sub_key` is
    removed from each row of it, leaving the rest of the row in place.
    """
    await use_case.handle(
        PurgeNodeTypeAttributeCommand(
            node_type_id=node_type_id, key=key, sub_key=sub_key
        ),
        actor,
    )
