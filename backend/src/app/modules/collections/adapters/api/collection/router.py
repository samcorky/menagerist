import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
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
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.collections.adapters.api.collection.schemas import (
    AddItemsRequest,
    AddItemsResponse,
    CollectionResponse,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from app.modules.collections.adapters.api.dependencies import (
    get_add_items_to_collection_use_case,
    get_create_collection_use_case,
    get_delete_collection_use_case,
    get_get_collection_use_case,
    get_list_collections_use_case,
    get_remove_item_from_collection_use_case,
    get_update_collection_use_case,
)
from app.modules.collections.application.add_items_to_collection import (
    AddItemsToCollection,
    AddItemsToCollectionCommand,
)
from app.modules.collections.application.create_collection import CreateCollection
from app.modules.collections.application.delete_collection import (
    DeleteCollection,
    DeleteCollectionCommand,
)
from app.modules.collections.application.get_collection import (
    CollectionSummary,
    GetCollection,
    GetCollectionQuery,
)
from app.modules.collections.application.list_collections import (
    ListCollections,
    ListCollectionsQuery,
)
from app.modules.collections.application.remove_item_from_collection import (
    RemoveItemFromCollection,
    RemoveItemFromCollectionCommand,
)
from app.modules.collections.application.update_collection import UpdateCollection
from app.modules.collections.domain.errors import (
    CollectionNotFoundError,
    InvalidCollectionError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ConflictError, ValidationError

router = APIRouter(
    prefix="/collection", tags=["Collections"], route_class=PermissionAwareRoute
)

_NOT_FOUND = error_response(
    CollectionNotFoundError,
    detail="Collection 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20 not found",
)


@router.post(
    "",
    response_model=CollectionResponse,
    status_code=201,
    operation_id="create_collection",
    responses={
        **error_response(
            ConflictError, detail="Collection with slug 'watchlist' already exists"
        ),
        **error_response(
            InvalidCollectionError,
            detail="A collection name must be 1 to 120 characters.",
        ),
    },
)
async def create_collection(
    payload: CreateCollectionRequest,
    use_case: Annotated[CreateCollection, Depends(get_create_collection_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> CollectionResponse:
    """Create a collection. The slug is derived from the name unless given."""
    collection = await use_case.handle(payload.to_command(), actor)
    return CollectionResponse.from_domain(
        CollectionSummary(collection=collection, item_count=0)
    )


@router.get(
    "",
    response_model=list[CollectionResponse],
    operation_id="list_collections",
    responses={**link_header_responses()},
)
async def list_collections(
    use_case: Annotated[ListCollections, Depends(get_list_collections_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    request: Request,
    response: Response,
    after: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    item_id: uuid.UUID | None = None,
) -> list[CollectionResponse]:
    """List collections with item counts, optionally only those holding an item."""
    result = await use_case.handle(
        ListCollectionsQuery(after=after, limit=limit + 1, item_id=item_id), actor
    )
    summaries = result.items
    if len(summaries) > limit:
        response.headers["Link"] = link_next_header(
            request, str(summaries[limit - 1].collection.id)
        )
    return [CollectionResponse.from_domain(s) for s in summaries[:limit]]


@router.get(
    "/{collection_id}",
    response_model=CollectionResponse,
    operation_id="get_collection",
    responses={**conditional_get_responses(), **_NOT_FOUND},
)
async def get_collection(
    collection_id: uuid.UUID,
    use_case: Annotated[GetCollection, Depends(get_get_collection_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    cond: ConditionalRequestDep,
) -> CollectionResponse | Response:
    """Fetch a single collection by id."""
    summary = await use_case.handle(
        GetCollectionQuery(collection_id=collection_id), actor
    )
    if earlier := cond.check_get(summary.collection, str(summary.item_count)):
        return earlier
    return CollectionResponse.from_domain(summary)


@router.patch(
    "/{collection_id}",
    response_model=CollectionResponse,
    operation_id="update_collection",
    responses={
        **conditional_patch_responses(),
        **_NOT_FOUND,
        **error_response(
            InvalidCollectionError,
            detail="A collection name must be 1 to 120 characters.",
        ),
    },
)
async def update_collection(
    collection_id: uuid.UUID,
    payload: UpdateCollectionRequest,
    get_usecase: Annotated[GetCollection, Depends(get_get_collection_use_case)],
    update_usecase: Annotated[
        UpdateCollection, Depends(get_update_collection_use_case)
    ],
    cond: ConditionalRequestDep,
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> CollectionResponse | Response:
    """Update a collection's name or description. `slug` is immutable."""
    current = await get_usecase.handle(
        GetCollectionQuery(collection_id=collection_id), actor
    )
    if earlier := cond.check_patch(current.collection, str(current.item_count)):
        return earlier
    collection = await update_usecase.handle(payload.to_command(collection_id), actor)
    cond.set_response_etag(collection, str(current.item_count))
    return CollectionResponse.from_domain(
        CollectionSummary(collection=collection, item_count=current.item_count)
    )


@router.delete(
    "/{collection_id}",
    status_code=204,
    operation_id="delete_collection",
    responses=_NOT_FOUND,
)
async def delete_collection(
    collection_id: uuid.UUID,
    use_case: Annotated[DeleteCollection, Depends(get_delete_collection_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Soft-delete a collection. Its items are untouched."""
    await use_case.handle(DeleteCollectionCommand(collection_id=collection_id), actor)


@router.put(
    "/{collection_id}/item",
    response_model=AddItemsResponse,
    operation_id="add_items_to_collection",
    responses={
        **_NOT_FOUND,
        **error_response(
            ValidationError, detail="Unknown or deleted items: 01978c3e-2b8b-7c3a"
        ),
    },
)
async def add_items_to_collection(
    collection_id: uuid.UUID,
    payload: AddItemsRequest,
    use_case: Annotated[
        AddItemsToCollection, Depends(get_add_items_to_collection_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> AddItemsResponse:
    """Put items on a collection. Items already on it are skipped."""
    added = await use_case.handle(
        AddItemsToCollectionCommand(
            collection_id=collection_id, item_ids=payload.item_ids
        ),
        actor,
    )
    return AddItemsResponse(added=added)


@router.delete(
    "/{collection_id}/item/{item_id}",
    status_code=204,
    operation_id="remove_item_from_collection",
    responses=_NOT_FOUND,
)
async def remove_item_from_collection(
    collection_id: uuid.UUID,
    item_id: uuid.UUID,
    use_case: Annotated[
        RemoveItemFromCollection, Depends(get_remove_item_from_collection_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> None:
    """Take an item off a collection. Removing an absent item is a no-op."""
    await use_case.handle(
        RemoveItemFromCollectionCommand(collection_id=collection_id, item_id=item_id),
        actor,
    )
