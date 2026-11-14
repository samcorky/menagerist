from typing import TYPE_CHECKING

from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.modules.transfer.adapters.persistence.run_repository import (
    SqlAlchemyRunRepository,
)
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork


def build_example_repos(session: AsyncSession) -> ExampleRepos:
    """Build an `ExampleRepos` bundle of SQLAlchemy repositories over `session`."""
    return ExampleRepos(runs=SqlAlchemyRunRepository(session))


def create_example_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> ExampleUnitOfWork:
    """Wrap a session factory in a SqlAlchemySessionUnitOfWork."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_example_repos)


def create_in_memory_example_uow(repos: ExampleRepos) -> ExampleUnitOfWork:
    """Wrap repos in an InMemoryUnitOfWork."""
    return InMemoryUnitOfWork(repos)
