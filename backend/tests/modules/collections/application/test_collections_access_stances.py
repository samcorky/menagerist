from typing import TYPE_CHECKING, Any

from app.modules.collections.application.add_items_to_collection import (
    AddItemsToCollection,
)
from app.modules.collections.application.claim_legacy_collections import (
    ClaimLegacyCollections,
)
from app.modules.collections.application.count_collection_items import (
    CountCollectionItems,
)
from app.modules.collections.application.create_collection import CreateCollection
from app.modules.collections.application.delete_collection import DeleteCollection
from app.modules.collections.application.get_collection import GetCollection
from app.modules.collections.application.list_collections import ListCollections
from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.application.remove_item_from_collection import (
    RemoveItemFromCollection,
)
from app.modules.collections.application.resolve_collection import ResolveCollection
from app.modules.collections.application.update_collection import UpdateCollection
from app.shared_kernel.access import Access, Content, System

if TYPE_CHECKING:
    from app.shared_kernel.cqrs import UseCase


READ = Content(CollectionPermission.COLLECTION_READ)
WRITE = Content(CollectionPermission.COLLECTION_WRITE)

STANCES: dict[type[UseCase[Any, Any]], Access] = {
    CountCollectionItems: READ,
    GetCollection: READ,
    ListCollections: READ,
    ResolveCollection: READ,
    AddItemsToCollection: WRITE,
    CreateCollection: WRITE,
    DeleteCollection: WRITE,
    RemoveItemFromCollection: WRITE,
    UpdateCollection: WRITE,
}


def test_collection_use_cases_need_the_collection_permissions() -> None:
    """Each person sees and changes only their own collections, given the permission."""
    assert {use_case: use_case.access for use_case in STANCES} == STANCES


def test_claim_jobs_are_system_only() -> None:
    """Only the system actor hands pre-account content to the first owner."""
    for use_case in (ClaimLegacyCollections,):
        assert use_case.access == System()
