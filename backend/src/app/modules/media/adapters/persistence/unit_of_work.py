from typing import TYPE_CHECKING

from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.ports.unit_of_work import MediaRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.media.ports.unit_of_work import MediaUnitOfWork


def _build_repos(session: AsyncSession) -> MediaRepos:
    return MediaRepos(assets=SqlAlchemyMediaAssetRepository(session))


def create_media_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> MediaUnitOfWork:
    """Wrap a session factory in a `SqlAlchemySessionUnitOfWork` for media."""
    return SqlAlchemySessionUnitOfWork(session_factory, _build_repos)


def create_in_memory_media_uow(repos: MediaRepos) -> MediaUnitOfWork:
    """Wrap repos in an `InMemoryUnitOfWork` for tests."""
    return InMemoryUnitOfWork(repos)
