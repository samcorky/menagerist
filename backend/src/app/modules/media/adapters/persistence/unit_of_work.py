from typing import TYPE_CHECKING

from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.adapters.persistence.media_attachment_repository import (
    SqlAlchemyMediaAttachmentRepository,
)
from app.modules.media.ports.unit_of_work import MediaRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.media.ports.unit_of_work import MediaUnitOfWork


def build_media_repos(session: AsyncSession) -> MediaRepos:
    """Build a `MediaRepos` bundle of SQLAlchemy repositories over `session`."""
    return MediaRepos(
        assets=SqlAlchemyMediaAssetRepository(session),
        attachments=SqlAlchemyMediaAttachmentRepository(session),
    )


def create_media_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> MediaUnitOfWork:
    """Wrap a session factory in a `SqlAlchemySessionUnitOfWork` for media."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_media_repos)


def create_in_memory_media_uow(repos: MediaRepos) -> MediaUnitOfWork:
    """Wrap repos in an `InMemoryUnitOfWork` for tests."""
    return InMemoryUnitOfWork(repos)


def make_in_memory_repos(
    *,
    assets: InMemoryMediaAttachmentRepository | None = None,
    attachments: InMemoryMediaAttachmentRepository | None = None,
) -> MediaRepos:
    """Build a `MediaRepos` with in-memory implementations for tests."""
    from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (  # noqa: E501
        InMemoryMediaAssetRepository,
    )

    return MediaRepos(
        assets=assets or InMemoryMediaAssetRepository(),  # type: ignore[arg-type]
        attachments=attachments or InMemoryMediaAttachmentRepository(),
    )
