import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.http.rate_limit import (
    RATE_LIMITED_RESPONSE,
    RateLimitBucket,
    rate_limited,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.transfer.adapters.api.bundle.schemas import (
    BUNDLE_EXAMPLE,
    IMPORT_PLAN_EXAMPLE,
    IMPORT_RESULT_EXAMPLE,
    BundleFile,
    BundleFileResponse,
    ImportPlanResponse,
    ImportResultResponse,
)
from app.modules.transfer.adapters.api.dependencies import (
    get_export_bundle_use_case,
    get_import_bundle_use_case,
    get_plan_bundle_import_use_case,
)
from app.modules.transfer.application.bundle_files import (
    BundleFileRequest,
    ExportBundle,
    ExportBundleQuery,
    ImportBundle,
    PlanBundleImport,
)
from app.modules.transfer.domain.bundle import BUNDLE_FORMAT, MAX_ITEMS
from app.modules.transfer.domain.errors import InvalidBundleError
from app.shared_kernel.actor import Actor

router = APIRouter(
    prefix="/bundles", tags=["Bundles"], route_class=PermissionAwareRoute
)

_INVALID = error_response(
    InvalidBundleError, detail="presets[0] needs definition, kind"
)


def _example(example: dict[str, Any]) -> dict[str, Any]:
    """Document `example` as the success response body."""
    return {"content": {"application/json": {"example": example}}}


@router.post(
    "/import/plan",
    response_model=ImportPlanResponse,
    operation_id="plan_bundle_import",
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={
        200: _example(IMPORT_PLAN_EXAMPLE),
        **_INVALID,
        **RATE_LIMITED_RESPONSE,
    },
)
async def plan_bundle_import(
    payload: BundleFile,
    use_case: Annotated[PlanBundleImport, Depends(get_plan_bundle_import_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ImportPlanResponse:
    """See what importing a file would do, without importing anything.

    Each thing in the file is `create`, or `unchanged` with the reason: you already
    have one the same, it repeats one earlier in the file, or the name is taken. A
    file the import would refuse is refused here in the same way.
    """
    plan = await use_case.handle(BundleFileRequest(data=payload.data()), actor)
    return ImportPlanResponse.from_domain(plan)


@router.post(
    "/import",
    response_model=ImportResultResponse,
    operation_id="import_bundle",
    dependencies=[Depends(rate_limited(RateLimitBucket.IMPORTS))],
    responses={
        200: _example(IMPORT_RESULT_EXAMPLE),
        **_INVALID,
        **RATE_LIMITED_RESPONSE,
    },
)
async def import_bundle(
    payload: BundleFile,
    use_case: Annotated[ImportBundle, Depends(get_import_bundle_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ImportResultResponse:
    """Import a file, such as a `menagerist-bundle` of saved fields.

    What you already have is skipped and counted. This does exactly what
    `POST /bundles/import/plan` says it will.
    """
    applied = await use_case.handle(BundleFileRequest(data=payload.data()), actor)
    return ImportResultResponse.from_domain(applied)


@router.get(
    "/export",
    response_model=BundleFileResponse,
    operation_id="export_bundle",
    responses={200: _example(BUNDLE_EXAMPLE), **_INVALID},
)
async def export_bundle(
    use_case: Annotated[ExportBundle, Depends(get_export_bundle_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    preset_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description="The saved lists, fields or groups to export."),
    ] = None,
    item_type_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description="The item types to export, with the saved lists they use."),
    ] = None,
    relationship_type_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description="The connection types to export."),
    ] = None,
    item_ids: Annotated[
        list[uuid.UUID] | None,
        Query(
            max_length=MAX_ITEMS,
            description="The items to export, with their types, the saved lists "
            + "those use, and the connections that join two of the items."
        ),
    ] = None,
    file_format: Annotated[
        str,
        Query(
            alias="format",
            description="The file format to write.",
            examples=[BUNDLE_FORMAT],
        ),
    ] = BUNDLE_FORMAT,
) -> dict[str, Any]:
    """Export saved lists, fields, groups, types and items as a file to import again.

    Choose at least one of the four kinds. In a `menagerist-bundle` file each
    `ref` is the id, so the same thing has the same ref in every file. A type
    brings the saved lists its fields use, and an item brings its type and the
    connections between the items chosen, so the file imports on its own; the file
    is `version` 3. At most 500 items can be exported at once.
    """
    return await use_case.handle(
        ExportBundleQuery(
            preset_ids=preset_ids or [],
            item_type_ids=item_type_ids or [],
            relationship_type_ids=relationship_type_ids or [],
            item_ids=item_ids or [],
            format=file_format,
        ),
        actor,
    )
