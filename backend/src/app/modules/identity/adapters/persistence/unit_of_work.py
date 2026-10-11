from typing import TYPE_CHECKING

from app.modules.identity.adapters.persistence.session_repository import (
    SqlAlchemySessionRepository,
)
from app.modules.identity.adapters.persistence.sign_in_attempt_repository import (
    SqlAlchemySignInAttemptRepository,
)
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.platform.unit_of_work import (
    SessionBoundUnitOfWork,
    SqlAlchemySessionUnitOfWork,
)
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork


def build_identity_repos(session: AsyncSession) -> IdentityRepos:
    """Build an `IdentityRepos` bundle of SQLAlchemy repositories over `session`."""
    return IdentityRepos(
        users=SqlAlchemyUserRepository(session),
        sessions=SqlAlchemySessionRepository(session),
        attempts=SqlAlchemySignInAttemptRepository(session),
    )


def create_identity_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> IdentityUnitOfWork:
    """Wrap a session factory in a SqlAlchemySessionUnitOfWork."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_identity_repos)


def create_identity_uow_on_session(session: AsyncSession) -> IdentityUnitOfWork:
    """Wrap an already-open session, so other work can share its transaction."""
    return SessionBoundUnitOfWork(session, build_identity_repos)


def create_in_memory_identity_uow(repos: IdentityRepos) -> IdentityUnitOfWork:
    """Wrap repos in an InMemoryUnitOfWork."""
    return InMemoryUnitOfWork(repos)
