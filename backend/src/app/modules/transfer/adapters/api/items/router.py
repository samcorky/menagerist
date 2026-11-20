from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import Json

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.http.rate_limit import (
    RATE_LIMITED_RESPONSE,
    RateLimitBucket,
    rate_limited,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.transfer.adapters.api.bundle.schemas import ImportPlanResponse
from app.modules.transfer.adapters.api.dependencies import (
    get_import_items_use_case,
    get_inspect_item_import_use_case,
    get_plan_item_import_use_case,
)
from app.modules.transfer.adapters.api.items.schemas import (
    INSPECT_EXAMPLE,
    ColumnMappingEntry,
    ItemImportInspectionResponse,
    ItemImportResultResponse,
)
from app.modules.transfer.application.item_import import (
    ImportItems,
    InspectItemImport,
    ItemImportRequest,
    PlanItemImport,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import (
    BundleConflictError,
    InvalidImportFileError,
)
from app.modules.transfer.domain.tabular import (
    MAX_IMPORT_BYTES,
    ColumnMapping,
    DayMonthOrder,
)
from app.shared_kernel.actor import Actor

router = APIRouter(
    prefix="/imports/items", tags=["Imports"], route_class=PermissionAwareRoute
)

_INVALID = error_response(
    InvalidImportFileError, detail="You have no item type called 'signature'."
)
_NOT_RUN = error_response(
    BundleConflictError, detail="Row 14, Signed on: '19th Aug' is not a date."
)

_FILE = Annotated[
    UploadFile,
    File(
        description="A CSV file with a header row, up to 10 MB, in UTF-8, UTF-16 or "
        + "Windows-1252 (what Excel's plain CSV writes)."
    ),
]
_ITEM_TYPE = Annotated[
    str, Form(description="The slug of the item type the rows become.")
]
_MAPPING = Annotated[
    Json[list[ColumnMappingEntry]],
    Form(
        description="Where each column goes, as JSON: a list of `column` and "
        + "`target`, or `extra` to keep the column as each item's own field.",
        examples=[
            '[{"column": "title", "target": "name"}, {"column": "paper", '
            + '"extra": {"key": "paper", "title": "Paper", "kind": "text"}}]'
        ],
    ),
]
_SEPARATOR = Annotated[
    str,
    Form(description="What separates several choices or tags in one cell."),
]
_DAY_MONTH_ORDER = Annotated[
    DayMonthOrder,
    Form(
        description="Which number of a date written as `03/04/2019` is the day. "
        + "Two-digit years: 00 to 49 are 2000 to 2049, 50 to 99 are 1950 to 1999."
    ),
]


async def _read(file: UploadFile) -> bytes:
    """Read the upload, stopping one byte past the limit so it can be refused."""
    return await file.read(MAX_IMPORT_BYTES + 1)


def _mapping(entries: list[ColumnMappingEntry]) -> tuple[ColumnMapping, ...]:
    return tuple(e.to_domain() for e in entries)


def _example(example: dict[str, Any]) -> dict[str, Any]:
    return {"content": {"application/json": {"example": example}}}


@router.post(
    "/inspect",
    response_model=ItemImportInspectionResponse,
    operation_id="inspect_item_import",
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={
        200: _example(INSPECT_EXAMPLE),
        **_INVALID,
        **RATE_LIMITED_RESPONSE,
    },
)
async def inspect_item_import(
    file: _FILE,
    item_type: _ITEM_TYPE,
    use_case: Annotated[InspectItemImport, Depends(get_inspect_item_import_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ItemImportInspectionResponse:
    """Read a CSV file and say what is in it, before importing anything.

    Returns the column names, the first rows, how many rows there are, the item
    type's fields, and a suggested mapping that matches each column to a field by its
    name. Nothing is stored; send the file again to preview and to import.
    """
    request = ItemImportRequest(data=await _read(file), item_type=item_type)
    return ItemImportInspectionResponse.from_domain(
        await use_case.handle(request, actor)
    )


@router.post(
    "/plan",
    response_model=ImportPlanResponse,
    operation_id="plan_item_import",
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={**_INVALID, **RATE_LIMITED_RESPONSE},
)
async def plan_item_import(
    file: _FILE,
    item_type: _ITEM_TYPE,
    mapping: _MAPPING,
    use_case: Annotated[PlanItemImport, Depends(get_plan_item_import_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    list_separator: _SEPARATOR = ",",
    day_month_order: _DAY_MONTH_ORDER = DayMonthOrder.DAY_FIRST,
) -> ImportPlanResponse:
    """See what importing a CSV file would do, without importing anything.

    Each row is an item to `create`. A value that cannot be imported, such as a date
    written as "19th Aug", is a blocker that names its row (the header is row 1) and
    field; while there are any, the plan is not `ready`.
    """
    request = ItemImportRequest(
        data=await _read(file),
        item_type=item_type,
        mapping=_mapping(mapping),
        list_separator=list_separator,
        day_month_order=day_month_order,
    )
    return ImportPlanResponse.from_domain(await use_case.handle(request, actor))


@router.post(
    "",
    response_model=ItemImportResultResponse,
    operation_id="import_items",
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={**_INVALID, **_NOT_RUN, **RATE_LIMITED_RESPONSE},
)
async def import_items(
    file: _FILE,
    item_type: _ITEM_TYPE,
    mapping: _MAPPING,
    use_case: Annotated[ImportItems, Depends(get_import_items_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    list_separator: _SEPARATOR = ",",
    day_month_order: _DAY_MONTH_ORDER = DayMonthOrder.DAY_FIRST,
) -> ItemImportResultResponse:
    """Import a CSV file as items of one item type.

    Plans the file again, as `POST /imports/items/plan` does, and creates the items
    only if nothing in it is a problem.
    """
    request = ItemImportRequest(
        data=await _read(file),
        item_type=item_type,
        mapping=_mapping(mapping),
        list_separator=list_separator,
        day_month_order=day_month_order,
    )
    applied = await use_case.handle(request, actor)
    return ItemImportResultResponse.from_domain(applied, EntityKind.ITEM)
