from typing import TYPE_CHECKING, Any

from app.modules.examples.application.claim_orphaned_installations import (
    ClaimOrphanedInstallations,
)
from app.modules.examples.application.install_example_pack import InstallExamplePack
from app.modules.examples.application.list_example_entities import ListExampleEntities
from app.modules.examples.application.list_example_packs import ListExamplePacks
from app.modules.examples.application.permissions import ExamplePermission
from app.modules.examples.application.uninstall_example_pack import UninstallExamplePack
from app.shared_kernel.access import Access, Content, System

if TYPE_CHECKING:
    from app.shared_kernel.cqrs import UseCase

READ = Content(ExamplePermission.PACK_READ)
INSTALL = Content(ExamplePermission.PACK_INSTALL)

STANCES: dict[type[UseCase[Any, Any]], Access] = {
    ListExampleEntities: READ,
    ListExamplePacks: READ,
    InstallExamplePack: INSTALL,
    UninstallExamplePack: INSTALL,
}


def test_installations_belong_to_their_owner() -> None:
    """Each person lists, installs and removes their own example sets."""
    assert {use_case: use_case.access for use_case in STANCES} == STANCES


def test_claiming_old_installations_is_a_system_job() -> None:
    """Only the system actor hands pre-account installations to the first owner."""
    assert ClaimOrphanedInstallations.access == System()
