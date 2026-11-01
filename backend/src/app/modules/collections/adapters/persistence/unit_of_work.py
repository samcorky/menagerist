from typing import TYPE_CHECKING

from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.adapters.persistence.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork


def build_collections_repos(session: AsyncSession) -> CollectionsRepos:
    """Build a `CollectionsRepos` bundle of SQLAlchemy repositories over `session`."""
    return CollectionsRepos(
        collections=SqlAlchemyCollectionRepository(session),
        memberships=SqlAlchemyMembershipRepository(session),
    )


def create_collections_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> CollectionsUnitOfWork:
    """Wrap a session factory in a SqlAlchemySessionUnitOfWork."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_collections_repos)


def create_in_memory_collections_uow(repos: CollectionsRepos) -> CollectionsUnitOfWork:
    """Wrap repos in an InMemoryUnitOfWork."""
    return InMemoryUnitOfWork(repos)
