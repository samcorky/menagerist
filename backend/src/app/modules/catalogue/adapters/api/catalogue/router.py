from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.catalogue.adapters.api.catalogue.schemas import (
    CATALOGUE_EXAMPLE,
    OUTCOME_EXAMPLE,
    CatalogueEntryResponse,
    InstallOutcomeResponse,
)
from app.modules.catalogue.adapters.api.dependencies import (
    get_install_catalogue_entry_use_case,
    get_list_catalogue_entries_use_case,
)
from app.modules.catalogue.application.install_catalogue_entry import (
    InstallCatalogueEntry,
    InstallCatalogueEntryCommand,
)
from app.modules.catalogue.application.list_catalogue_entries import (
    ListCatalogueEntries,
    ListCatalogueEntriesQuery,
)
from app.modules.catalogue.domain.errors import CatalogueEntryNotFoundError
from app.shared_kernel.actor import Actor

router = APIRouter(
    prefix="/catalogue", tags=["Catalogue"], route_class=PermissionAwareRoute
)

_NOT_FOUND = error_response(
    CatalogueEntryNotFoundError, detail="Catalogue entry 'condition-grades' not found"
)


def _example(example: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    """Document `example` as the success response body."""
    return {"content": {"application/json": {"example": example}}}


@router.get(
    "",
    response_model=list[CatalogueEntryResponse],
    operation_id="list_catalogue_entries",
    responses={200: _example(CATALOGUE_EXAMPLE)},
)
async def list_catalogue_entries(
    use_case: Annotated[
        ListCatalogueEntries, Depends(get_list_catalogue_entries_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[CatalogueEntryResponse]:
    """List the saved lists, fields, field groups and starter types you can add.

    `present` of `total` says how much of an entry you already have; `installed` is
    true when it is all there.
    """
    statuses = await use_case.handle(ListCatalogueEntriesQuery(), actor)
    return [CatalogueEntryResponse.from_domain(s) for s in statuses]


@router.put(
    "/{entry_id}/installation",
    response_model=InstallOutcomeResponse,
    operation_id="install_catalogue_entry",
    responses={**_NOT_FOUND, 200: _example(OUTCOME_EXAMPLE)},
)
async def install_catalogue_entry(
    entry_id: Annotated[str, Path(description="The id of the entry to add.")],
    use_case: Annotated[
        InstallCatalogueEntry, Depends(get_install_catalogue_entry_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> InstallOutcomeResponse:
    """Add an entry to your own saved fields or types.

    What is added is yours to edit and delete. Anything you already have is skipped
    and counted: an identical saved list, field or field group, or a type whose name
    is taken. Adding the same entry again is safe.
    """
    result = await use_case.handle(
        InstallCatalogueEntryCommand(entry_id=entry_id), actor
    )
    return InstallOutcomeResponse.from_domain(result)
