from typing import TYPE_CHECKING

from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.edge_type_repository import (
    SqlAlchemyEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
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

    from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
        EdgeStore,
    )
    from app.modules.graph.ports.collection_definitions import CollectionDefinitions
    from app.modules.graph.ports.external_conditions import ExternalConditions
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork


def build_graph_repos(
    session: AsyncSession,
    *,
    external: ExternalConditions | None = None,
    definitions: CollectionDefinitions | None = None,
) -> GraphRepos:
    """Build a `GraphRepos` bundle of SQLAlchemy repositories over `session`.

    Searches that use media or collection conditions need `external` (and
    `definitions` for smart collections); without them those conditions match
    nothing.
    """
    return GraphRepos(
        nodes=SqlAlchemyNodeRepository(session, external),
        edges=SqlAlchemyEdgeRepository(session),
        node_types=SqlAlchemyNodeTypeRepository(session),
        edge_types=SqlAlchemyEdgeTypeRepository(session),
        external=external,
        definitions=definitions,
    )


def build_in_memory_graph_repos(
    *,
    external: ExternalConditions | None = None,
    definitions: CollectionDefinitions | None = None,
) -> GraphRepos:
    """Build a `GraphRepos` bundle of in-memory repositories.

    The node and edge repositories share one edge store, so searches can
    evaluate connection conditions over the edges written through `edges`.
    """
    store: EdgeStore = {}
    return GraphRepos(
        nodes=InMemoryNodeRepository(external, store),
        edges=InMemoryEdgeRepository(store),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
        external=external,
        definitions=definitions,
    )


def create_graph_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> GraphUnitOfWork:
    """Wrap a session factory in a SqlAlchemySessionUnitOfWork."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_graph_repos)


def create_in_memory_graph_uow(repos: GraphRepos) -> GraphUnitOfWork:
    """Wrap repos in an InMemoryUnitOfWork."""
    return InMemoryUnitOfWork(repos)
