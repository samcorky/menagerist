from typing import Annotated

from fastapi import APIRouter, Depends

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.examples.adapters.api.dependencies import (
    get_install_example_pack_use_case,
    get_list_example_entities_use_case,
    get_list_example_packs_use_case,
    get_uninstall_example_pack_use_case,
)
from app.modules.examples.adapters.api.example.schemas import (
    ExampleEntitiesResponse,
    ExamplePackResponse,
    InstallResultResponse,
    UninstallResultResponse,
)
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.application.list_example_entities import (
    ListExampleEntities,
    ListExampleEntitiesQuery,
)
from app.modules.examples.application.list_example_packs import (
    ListExamplePacks,
    ListExamplePacksQuery,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
)
from app.modules.examples.domain.errors import (
    PackAlreadyInstalledError,
    PackNotFoundError,
    PackNotInstalledError,
)
from app.shared_kernel.actor import Actor

router = APIRouter(
    prefix="/example", tags=["Examples"], route_class=PermissionAwareRoute
)

_NOT_FOUND = error_response(PackNotFoundError, detail="Example pack 'vinyl' not found")
# One 409 entry per route: a response status can only be documented once. The install
# route's 409 also covers a taken type name (`SlugClashError`) and a missing required
# set (`RequirementsNotMetError`); the uninstall 409 also covers a dependant add-on
# (`RequiredByInstalledPackError`). Each docstring says so.
_ALREADY = error_response(
    PackAlreadyInstalledError, detail="'vinyl' is already installed."
)
_NOT_INSTALLED = error_response(
    PackNotInstalledError, detail="'vinyl' is not installed"
)


@router.get(
    "", response_model=list[ExamplePackResponse], operation_id="list_example_packs"
)
async def list_example_packs(
    use_case: Annotated[ListExamplePacks, Depends(get_list_example_packs_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[ExamplePackResponse]:
    """List the example sets this server ships and which are installed."""
    statuses = await use_case.handle(ListExamplePacksQuery(), actor)
    return [ExamplePackResponse.from_status(s) for s in statuses]


@router.get(
    "/entities",
    response_model=ExampleEntitiesResponse,
    operation_id="list_example_entities",
)
async def list_example_entities(
    use_case: Annotated[
        ListExampleEntities, Depends(get_list_example_entities_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ExampleEntitiesResponse:
    """List the items, item types and collections that added example sets own."""
    entities = await use_case.handle(ListExampleEntitiesQuery(), actor)
    return ExampleEntitiesResponse.from_domain(entities)


@router.put(
    "/{pack_id}/installation",
    response_model=InstallResultResponse,
    operation_id="install_example_pack",
    responses={**_NOT_FOUND, **_ALREADY},
)
async def install_example_pack(
    pack_id: str,
    use_case: Annotated[InstallExamplePack, Depends(get_install_example_pack_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> InstallResultResponse:
    """Add an example set: its item types, items, connections and saved lists.

    Anything an earlier removal kept (because you changed it or used it) and that
    still exists is taken back rather than created again; `adopted` counts those and
    `created` counts only what is new. A collection taken back is left as you have
    it, so items created this time are not added to it.

    Returns 409 if the set is already added, if you already have an item type or
    relationship type with a name it needs that is not a kept example, or if it is an
    add-on and a set it needs is not added yet (nothing is created in any case).
    """
    result = await use_case.handle(InstallExamplePackCommand(pack_id=pack_id), actor)
    return InstallResultResponse.from_domain(result)


@router.delete(
    "/{pack_id}/installation",
    response_model=UninstallResultResponse,
    operation_id="uninstall_example_pack",
    responses={**_NOT_FOUND, **_NOT_INSTALLED},
)
async def uninstall_example_pack(
    pack_id: str,
    use_case: Annotated[
        UninstallExamplePack, Depends(get_uninstall_example_pack_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> UninstallResultResponse:
    """Remove an example set. Anything you changed or connected to is kept.

    Returns 409 if the set is not added, or if added add-ons still need it (the
    message names them; nothing is removed).
    """
    result = await use_case.handle(UninstallExamplePackCommand(pack_id=pack_id), actor)
    return UninstallResultResponse.from_domain(result)
