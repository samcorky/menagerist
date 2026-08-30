from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.shared_kernel.unit_of_work import UnitOfWork

if TYPE_CHECKING:
    from app.modules.graph.ports.edge_repository import EdgeRepository
    from app.modules.graph.ports.node_repository import NodeRepository
    from app.modules.graph.ports.node_type_repository import NodeTypeRepository


@dataclass(kw_only=True)
class GraphRepos:
    """The graph module's repository bundle - node, edge, and node type."""

    nodes: "NodeRepository"
    edges: "EdgeRepository"
    node_types: "NodeTypeRepository"


GraphUnitOfWork = UnitOfWork[GraphRepos]
