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
from app.modules.collections.application.remove_item_from_collection import (
    RemoveItemFromCollection,
)
from app.modules.collections.application.resolve_collection import ResolveCollection
from app.modules.collections.application.update_collection import UpdateCollection
from app.shared_kernel.access import Content, System


def test_content_use_cases_are_owner_scoped() -> None:
    """Each person sees and changes only their own content."""
    for use_case in (
        AddItemsToCollection,
        CountCollectionItems,
        CreateCollection,
        DeleteCollection,
        GetCollection,
        ListCollections,
        RemoveItemFromCollection,
        ResolveCollection,
        UpdateCollection,
    ):
        assert use_case.access == Content()


def test_claim_jobs_are_system_only() -> None:
    """Only the system actor hands pre-account content to the first owner."""
    for use_case in (ClaimLegacyCollections,):
        assert use_case.access == System()
