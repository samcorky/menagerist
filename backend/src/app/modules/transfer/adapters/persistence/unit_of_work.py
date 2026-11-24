from typing import TYPE_CHECKING

from app.modules.transfer.adapters.persistence.import_repository import (
    SqlAlchemyItemImportRepository,
)
from app.modules.transfer.adapters.persistence.source_link_repository import (
    SqlAlchemySourceLinkRepository,
)
from app.modules.transfer.ports.unit_of_work import TransferRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.transfer.ports.unit_of_work import TransferUnitOfWork


def build_transfer_repos(session: AsyncSession) -> TransferRepos:
    """Build a `TransferRepos` bundle of SQLAlchemy repositories over `session`."""
    return TransferRepos(
        links=SqlAlchemySourceLinkRepository(session),
        imports=SqlAlchemyItemImportRepository(session),
    )


def create_transfer_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> TransferUnitOfWork:
    """Wrap a session factory in a SqlAlchemySessionUnitOfWork."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_transfer_repos)


def create_in_memory_transfer_uow(repos: TransferRepos) -> TransferUnitOfWork:
    """Wrap repos in an InMemoryUnitOfWork."""
    return InMemoryUnitOfWork(repos)
