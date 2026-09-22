from typing import TYPE_CHECKING

from app.modules.presets.adapters.persistence.preset_repository import (
    SqlAlchemyPresetRepository,
)
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.presets.ports.unit_of_work import PresetUnitOfWork


def build_preset_repos(session: AsyncSession) -> PresetRepos:
    """Build a `PresetRepos` bundle of SQLAlchemy repositories over `session`."""
    return PresetRepos(presets=SqlAlchemyPresetRepository(session))


def create_preset_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> PresetUnitOfWork:
    """Wrap a session factory in a SqlAlchemySessionUnitOfWork."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_preset_repos)


def create_in_memory_preset_uow(repos: PresetRepos) -> PresetUnitOfWork:
    """Wrap repos in an InMemoryUnitOfWork."""
    return InMemoryUnitOfWork(repos)
