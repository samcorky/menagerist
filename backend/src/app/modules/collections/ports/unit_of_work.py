from dataclasses import dataclass

from app.modules.collections.ports.collection_repository import CollectionRepository
from app.modules.collections.ports.membership_repository import MembershipRepository
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class CollectionsRepos:
    """The collections module's repository bundle."""

    collections: CollectionRepository
    memberships: MembershipRepository


CollectionsUnitOfWork = UnitOfWork[CollectionsRepos]
