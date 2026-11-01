"""Compose SQLAlchemy and in-memory adapters using shared units of work."""

from typing import TYPE_CHECKING

from app.modules.system.adapters.persistence.in_memory_update_check_store import (
    InMemoryUpdateCheckStore,
)
from app.modules.system.adapters.persistence.update_check_store import (
    SqlAlchemyUpdateCheckStore,
)
from app.modules.system.ports.unit_of_work import SystemRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.system.ports.unit_of_work import SystemUnitOfWork


def build_system_repos(session: AsyncSession) -> SystemRepos:
    """Bind the system ports to the caller's existing transaction."""
    return SystemRepos(updates=SqlAlchemyUpdateCheckStore(session))


def create_system_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> SystemUnitOfWork:
    """Use the common SQLAlchemy unit of work."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_system_repos)


def create_in_memory_system_uow(
    updates: InMemoryUpdateCheckStore | None = None,
) -> InMemoryUnitOfWork[SystemRepos]:
    """Use the standard in-memory transaction signal implementation."""
    return InMemoryUnitOfWork(
        SystemRepos(
            updates=updates if updates is not None else InMemoryUpdateCheckStore()
        )
    )
