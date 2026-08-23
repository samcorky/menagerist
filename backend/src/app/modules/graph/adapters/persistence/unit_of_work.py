from typing import TYPE_CHECKING

from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork


def create_in_memory_graph_uow(repos: GraphRepos) -> GraphUnitOfWork:
    """Wrap `repos` in an `InMemoryUnitOfWork` - the fast-test/in-memory adapter."""
    return InMemoryUnitOfWork(repos)
