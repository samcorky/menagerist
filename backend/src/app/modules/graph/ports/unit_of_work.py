from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.shared_kernel.unit_of_work import UnitOfWork

if TYPE_CHECKING:
    from app.modules.graph.ports.edge_repository import EdgeRepository
    from app.modules.graph.ports.node_repository import NodeRepository


@dataclass(kw_only=True)
class GraphRepos:
    """The graph module's repository bundle - nodes and edges."""

    nodes: "NodeRepository"
    edges: "EdgeRepository"


GraphUnitOfWork = UnitOfWork[GraphRepos]
