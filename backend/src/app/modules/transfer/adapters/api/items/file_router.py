"""CSV files uploaded once, then inspected, previewed and imported by id.

The import itself runs on the worker; its progress is read back from the file.
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.http_headers import (
    paging_responses,
    set_page_headers,
)
from app.entrypoints.api.shared.http.parameters import (
    ImportFileId,
    NewestFirstPageParams,
)
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.http.rate_limit import (
    RATE_LIMITED_RESPONSE,
    RateLimitBucket,
    rate_limited,
)
from app.entrypoints.api.shared.http.upload_limit_middleware import (
    PAYLOAD_TOO_LARGE_RESPONSE,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.transfer.adapters.api.bundle.schemas import ImportPlanResponse
from app.modules.transfer.adapters.api.dependencies import (
    get_delete_item_import_use_case,
    get_get_item_import_use_case,
    get_inspect_stored_item_import_use_case,
    get_list_item_imports_use_case,
    get_plan_stored_item_import_use_case,
    get_queue_item_import_use_case,
    get_upload_item_import_use_case,
)
from app.modules.transfer.adapters.api.items.file_schemas import (
    ImportOptionsBody,
    InspectImportFileBody,
    ItemImportResponse,
)
from app.modules.transfer.adapters.api.items.schemas import (
    INSPECT_EXAMPLE,
    ItemImportInspectionResponse,
)
from app.modules.transfer.application.stored_imports import (
    DeleteItemImport,
    GetItemImport,
    InspectStoredImportQuery,
    InspectStoredItemImport,
    ItemImportQuery,
    ItemImportSort,
    ItemImportView,
    ListItemImports,
    ListItemImportsQuery,
    PlanStoredItemImport,
    QueueItemImport,
    QueueItemImportCommand,
    StoredImportCommand,
    UploadItemImport,
    UploadItemImportCommand,
)
from app.modules.transfer.domain.errors import (
    ImportFileTooLargeError,
    ImportNotFoundError,
    InvalidImportFileError,
    InvalidImportStateError,
)
from app.shared_kernel.actor import Actor

router = APIRouter(
    prefix="/imports/items/files", tags=["Imports"], route_class=PermissionAwareRoute
)

_NOT_FOUND = error_response(
    ImportNotFoundError,
    detail="You have no uploaded file 01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e40.",
)
_GONE = error_response(
    InvalidImportStateError,
    detail="The uploaded file is no longer stored. Upload it again.",
)
_INVALID = error_response(
    InvalidImportFileError, detail="You have no item type called 'signature'."
)
_CSV_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "text/csv": {
                "schema": {
                    "type": "string",
                    "format": "binary",
                    "description": "A CSV file with a header row, up to 50 MB, in "
                    + "UTF-8, UTF-16 or Windows-1252 (what Excel's plain CSV writes).",
                }
            }
        },
    }
}
_LINKS = {
    "GetImportFile": {
        "operationId": "get_item_import_file",
        "parameters": {"file_id": "$response.body#/id"},
        "description": "Read the file's status, progress and result.",
    },
    "DeleteImportFile": {
        "operationId": "delete_item_import_file",
        "parameters": {"file_id": "$response.body#/id"},
        "description": "Remove the file.",
    },
}
_FILE_ID = ImportFileId


def _response(view: ItemImportView) -> ItemImportResponse:
    return ItemImportResponse.from_domain(view)


def _example(example: dict[str, Any]) -> dict[str, Any]:
    return {"content": {"application/json": {"example": example}}}


@router.post(
    "",
    status_code=201,
    response_model=ItemImportResponse,
    operation_id="upload_item_import_file",
    openapi_extra=_CSV_BODY,
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={
        201: {"links": _LINKS},
        **error_response(
            ImportFileTooLargeError, detail="The file is over the 50 MB limit."
        ),
        **PAYLOAD_TOO_LARGE_RESPONSE,
        **RATE_LIMITED_RESPONSE,
    },
)
async def upload_item_import_file(
    request: Request,
    use_case: Annotated[UploadItemImport, Depends(get_upload_item_import_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    filename: Annotated[
        str,
        Header(
            alias="X-Filename",
            description="The file's name, percent-encoded so any name fits.",
        ),
    ] = "import.csv",
) -> ItemImportResponse:
    """Upload a CSV file to import, once, as the request body.

    The file is kept privately for a day. Inspect it, preview it and import it by
    its id; it is removed once its import finishes.
    """
    item = await use_case.handle(
        UploadItemImportCommand(
            filename=unquote(filename), chunks=request.stream(), now=datetime.now(UTC)
        ),
        actor,
    )
    return _response(ItemImportView(item=item, ahead=None))


@router.get(
    "",
    response_model=list[ItemImportResponse],
    operation_id="list_item_import_files",
    responses=paging_responses("Uploaded files"),
)
async def list_item_import_files(
    request: Request,
    response: Response,
    use_case: Annotated[ListItemImports, Depends(get_list_item_imports_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    page: Annotated[NewestFirstPageParams[ItemImportSort], Query()],
) -> list[ItemImportResponse]:
    """List your uploaded files and their imports, newest first unless sorted."""
    result = await use_case.handle(
        ListItemImportsQuery(
            after=page.cursor, limit=page.limit, sort=page.sort, order=page.order
        ),
        actor,
    )
    set_page_headers(request, response, result)
    return [_response(view) for view in result.items]


@router.get(
    "/{file_id}",
    response_model=ItemImportResponse,
    operation_id="get_item_import_file",
    responses={**_NOT_FOUND},
)
async def get_item_import_file(
    file_id: _FILE_ID,
    use_case: Annotated[GetItemImport, Depends(get_get_item_import_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ItemImportResponse:
    """Read an uploaded file's status, and its import's progress and result."""
    return _response(await use_case.handle(ItemImportQuery(import_id=file_id), actor))


@router.delete(
    "/{file_id}",
    status_code=204,
    operation_id="delete_item_import_file",
    responses={**_NOT_FOUND, **_GONE},
)
async def delete_item_import_file(
    file_id: _FILE_ID,
    use_case: Annotated[DeleteItemImport, Depends(get_delete_item_import_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> Response:
    """Remove an uploaded file; one waiting to import is taken out of the queue.

    A file being imported now cannot be removed.
    """
    await use_case.handle(ItemImportQuery(import_id=file_id), actor)
    return Response(status_code=204)


@router.post(
    "/{file_id}/inspect",
    response_model=ItemImportInspectionResponse,
    operation_id="inspect_item_import_file",
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={
        200: _example(INSPECT_EXAMPLE),
        **_NOT_FOUND,
        **_INVALID,
        **RATE_LIMITED_RESPONSE,
    },
)
async def inspect_item_import_file(
    file_id: _FILE_ID,
    body: InspectImportFileBody,
    use_case: Annotated[
        InspectStoredItemImport, Depends(get_inspect_stored_item_import_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ItemImportInspectionResponse:
    """Say what is in an uploaded file, as `POST /imports/items/inspect` does."""
    return ItemImportInspectionResponse.from_domain(
        await use_case.handle(
            InspectStoredImportQuery(import_id=file_id, item_type=body.item_type),
            actor,
        )
    )


@router.post(
    "/{file_id}/plan",
    response_model=ImportPlanResponse,
    operation_id="plan_item_import_file",
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={**_NOT_FOUND, **_INVALID, **RATE_LIMITED_RESPONSE},
)
async def plan_item_import_file(
    file_id: _FILE_ID,
    body: ImportOptionsBody,
    use_case: Annotated[
        PlanStoredItemImport, Depends(get_plan_stored_item_import_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ImportPlanResponse:
    """See what importing an uploaded file would do, as `POST /imports/items/plan`."""
    return ImportPlanResponse.from_domain(
        await use_case.handle(
            StoredImportCommand(import_id=file_id, options=body.to_domain()), actor
        )
    )


@router.post(
    "/{file_id}/import",
    status_code=202,
    response_model=ItemImportResponse,
    operation_id="import_item_import_file",
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={
        202: {"links": {"GetImportFile": _LINKS["GetImportFile"]}},
        **_NOT_FOUND,
        **error_response(
            InvalidImportStateError,
            detail="This import is queued, so it cannot do that.",
        ),
        **RATE_LIMITED_RESPONSE,
    },
)
async def import_item_import_file(
    file_id: _FILE_ID,
    body: ImportOptionsBody,
    use_case: Annotated[QueueItemImport, Depends(get_queue_item_import_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ItemImportResponse:
    """Import an uploaded file in the background.

    Imports run one at a time, taking turns between people; `ahead` says how many
    run before this one. Read the file's progress with `GET`. The worker plans the
    file again as it starts, so a problem found then fails the import with the
    preview's message.
    """
    return _response(
        await use_case.handle(
            QueueItemImportCommand(
                import_id=file_id, options=body.to_domain(), now=datetime.now(UTC)
            ),
            actor,
        )
    )
