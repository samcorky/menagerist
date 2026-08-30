from typing import TYPE_CHECKING

from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.adapters.persistence.node_type_repository import (
    SqlAlchemyNodeTypeRepository,
)
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork


def _build_repos(session: AsyncSession) -> GraphRepos:
    return GraphRepos(
        nodes=SqlAlchemyNodeRepository(session),
        edges=SqlAlchemyEdgeRepository(session),
        node_types=SqlAlchemyNodeTypeRepository(session),
    )


def create_graph_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> GraphUnitOfWork:
    """Wrap a session factory in a `SqlAlchemySessionUnitOfWork` - the real adapter."""
    return SqlAlchemySessionUnitOfWork(session_factory, _build_repos)


def create_in_memory_graph_uow(repos: GraphRepos) -> GraphUnitOfWork:
    """Wrap `repos` in an `InMemoryUnitOfWork` - the fast-test/in-memory adapter."""
    return InMemoryUnitOfWork(repos)
