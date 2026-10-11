import uuid

from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_in_memory_collections_uow,
)
from app.modules.collections.application.claim_legacy_collections import (
    ClaimLegacyCollections,
    ClaimLegacyCollectionsCommand,
)
from app.modules.collections.domain.collection import Collection
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.slug import Slug


async def test_claims_both_legacy_owners_and_commits() -> None:
    """Collections owned by UUID(0) or UUID(1) move; a real user's stay."""
    collections = InMemoryCollectionRepository()
    uow = create_in_memory_collections_uow(
        CollectionsRepos(
            collections=collections,
            memberships=InMemoryMembershipRepository(collections),
        )
    )
    system = Collection.create(name="a", slug=Slug("a"), owner_id=uuid.UUID(int=0))
    legacy = Collection.create(name="b", slug=Slug("b"), owner_id=uuid.UUID(int=1))
    real = Collection.create(name="c", slug=Slug("c"), owner_id=uuid.uuid7())
    for collection in (system, legacy, real):
        await collections.add(collection)
    owner = uuid.uuid7()

    count = await ClaimLegacyCollections(uow).handle(
        ClaimLegacyCollectionsCommand(owner_id=owner), SYSTEM_ACTOR
    )

    assert count == 2
    assert system.owner_id == legacy.owner_id == owner
    assert real.owner_id != owner
    assert getattr(uow, "committed", False)
