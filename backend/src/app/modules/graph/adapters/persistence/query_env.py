from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.modules.graph.ports.external_conditions import ExternalConditions
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.edge import Edge
    from app.modules.graph.domain.node import Node


class Links(Protocol):
    """The in-memory evaluator's view of connections."""

    def connected(
        self, node_id: uuid.UUID, scope: ContentFilter
    ) -> list[tuple[Edge, Node]]:
        """Live connections in `scope` touching the item, each with its far item.

        Only far items that are live and in `scope` are returned.
        """
        ...


@dataclass(frozen=True, kw_only=True)
class QueryEnv:
    """What a leaf needs beyond the item: the scope and the external data source.

    With no `external`, media and manual-collection conditions match nothing.
    With no `links`, no item has a connection.
    """

    scope: ContentFilter
    external: ExternalConditions | None = None
    links: Links | None = None
