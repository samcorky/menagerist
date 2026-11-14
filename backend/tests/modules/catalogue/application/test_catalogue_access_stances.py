from typing import TYPE_CHECKING, Any

from app.modules.catalogue.application.install_catalogue_entry import (
    InstallCatalogueEntry,
)
from app.modules.catalogue.application.list_catalogue_entries import (
    ListCatalogueEntries,
)
from app.modules.catalogue.application.permissions import CataloguePermission
from app.modules.catalogue.application.plan_catalogue_entry_install import (
    PlanCatalogueEntryInstall,
)
from app.shared_kernel.access import Access, Requires

if TYPE_CHECKING:
    from app.shared_kernel.cqrs import UseCase

STANCES: dict[type[UseCase[Any, Any]], Access] = {
    ListCatalogueEntries: Requires(CataloguePermission.ENTRY_READ),
    InstallCatalogueEntry: Requires(CataloguePermission.ENTRY_INSTALL),
    PlanCatalogueEntryInstall: Requires(CataloguePermission.ENTRY_INSTALL),
}


def test_the_catalogue_is_gated_by_its_own_permissions() -> None:
    """The catalogue is gated by its own permissions."""
    assert {use_case: use_case.access for use_case in STANCES} == STANCES
