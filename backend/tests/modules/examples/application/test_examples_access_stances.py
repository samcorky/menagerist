from app.modules.examples.application.claim_orphaned_installations import (
    ClaimOrphanedInstallations,
)
from app.modules.examples.application.install_example_pack import InstallExamplePack
from app.modules.examples.application.list_example_entities import ListExampleEntities
from app.modules.examples.application.list_example_packs import ListExamplePacks
from app.modules.examples.application.uninstall_example_pack import UninstallExamplePack
from app.shared_kernel.access import Content, System


def test_installations_belong_to_their_owner() -> None:
    """Each person installs, lists and removes their own example sets."""
    for use_case in (
        InstallExamplePack,
        ListExampleEntities,
        ListExamplePacks,
        UninstallExamplePack,
    ):
        assert use_case.access == Content()


def test_claiming_old_installations_is_a_system_job() -> None:
    """Only the system actor hands pre-account installations to the first owner."""
    assert ClaimOrphanedInstallations.access == System()
