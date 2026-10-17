import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.conditional_request import ConditionalRequestDep
from app.entrypoints.api.shared.http.http_headers import (
    conditional_get_responses,
    conditional_patch_responses,
    link_header_responses,
    link_next_header,
)
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.collections.adapters.api.collection.schemas import (
    AddItemsRequest,
    AddItemsResponse,
    CollectionCountResponse,
    CollectionResponse,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from app.modules.collections.adapters.api.dependencies import (
    get_add_items_to_collection_use_case,
    get_count_collection_items_use_case,
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
from app.modules.collections.application.count_collection_items import (
    CountCollectionItems,
    CountCollectionItemsQuery,
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
from app.modules.collections.domain.collection import Collection, CollectionKind
from app.modules.collections.domain.errors import (
    CollectionKindError,
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
_SMART = error_response(
    CollectionKindError,
    detail="Items cannot be added to or removed from a smart collection.",
)


def _is_smart(collection: Collection) -> bool:
    return collection.kind is CollectionKind.DYNAMIC


def _etag_extra(summary: CollectionSummary) -> str:
    """The state the body shows that does not move `updated_at`.

    A manual collection shows only its count. A smart one also shows whether
    the count is capped and its warnings, which change as items and fields do.
    """
    if not _is_smart(summary.collection):
        return str(summary.item_count)
    warnings = sorted([w.path, w.message] for w in summary.warnings)
    digest = hashlib.sha256(json.dumps(warnings).encode()).hexdigest()[:16]
    return f"{summary.item_count}:{int(summary.item_count_capped)}:{digest}"


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
    get_usecase: Annotated[GetCollection, Depends(get_get_collection_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> CollectionResponse:
    """Create a collection. The slug is derived from the name unless given.

    A `definition` makes it a smart collection, whose items are those matching it.
    """
    collection = await use_case.handle(payload.to_command(), actor)
    if not _is_smart(collection):
        return CollectionResponse.from_domain(
            CollectionSummary(collection=collection, item_count=0)
        )
    summary = await get_usecase.handle(
        GetCollectionQuery(collection_id=collection.id), actor
    )
    return CollectionResponse.from_domain(summary)


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
    q: Annotated[
        str | None,
        Query(
            max_length=200,
            description=(
                "Keep collections whose name or description contains this text."
            ),
        ),
    ] = None,
) -> list[CollectionResponse]:
    """List collections with item counts, optionally only those holding an item."""
    result = await use_case.handle(
        ListCollectionsQuery(after=after, limit=limit + 1, item_id=item_id, q=q), actor
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
    """Fetch a single collection by id, with a smart collection's warnings."""
    summary = await use_case.handle(
        GetCollectionQuery(collection_id=collection_id), actor
    )
    # A smart collection's count moves without `updated_at`, so dates cannot 304.
    if earlier := cond.check_get(
        summary.collection,
        _etag_extra(summary),
        honour_if_modified_since=not _is_smart(summary.collection),
    ):
        return earlier
    return CollectionResponse.from_domain(summary)


@router.get(
    "/{collection_id}/count",
    response_model=CollectionCountResponse,
    operation_id="count_collection_items",
    responses=_NOT_FOUND,
)
async def count_collection_items(
    collection_id: uuid.UUID,
    use_case: Annotated[
        CountCollectionItems, Depends(get_count_collection_items_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> CollectionCountResponse:
    """Count a collection's items exactly, with no cap.

    A smart collection's `item_count` stops at 1000; this does not.
    """
    count = await use_case.handle(
        CountCollectionItemsQuery(collection_id=collection_id), actor
    )
    return CollectionCountResponse(count=count)


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
        **error_response(
            CollectionKindError,
            detail="Only a smart collection has a definition.",
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
    """Update a collection's name, description or smart definition.

    `slug` and the kind are immutable.
    """
    current = await get_usecase.handle(
        GetCollectionQuery(collection_id=collection_id), actor
    )
    if earlier := cond.check_patch(current.collection, _etag_extra(current)):
        return earlier
    collection = await update_usecase.handle(payload.to_command(collection_id), actor)
    if _is_smart(collection):
        # The definition may have changed, and with it the count and warnings.
        summary = await get_usecase.handle(
            GetCollectionQuery(collection_id=collection_id), actor
        )
    else:
        summary = CollectionSummary(
            collection=collection, item_count=current.item_count
        )
    cond.set_response_etag(summary.collection, _etag_extra(summary))
    return CollectionResponse.from_domain(summary)


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
        **_SMART,
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
    responses={**_NOT_FOUND, **_SMART},
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
