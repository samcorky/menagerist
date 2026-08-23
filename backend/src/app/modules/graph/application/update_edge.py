import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.errors import EdgeNotFoundError

if TYPE_CHECKING:
    from app.modules.graph.domain.edge import Edge
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class UpdateEdgeCommand:
    """Request to update an edge's editable fields.

    `attributes` left as `None` is unchanged - `source_id`/`target_id`/`type`
    aren't editable.
    """

    edge_id: uuid.UUID
    attributes: dict[str, Any] | None = field(default=None)


class UpdateEdge:
    """Update an existing edge's editable fields."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: UpdateEdgeCommand, actor: Actor) -> Edge:
        """Apply `command`'s changes to the edge and commit."""
        async with self._uow as repos:
            edge = await repos.edges.get(command.edge_id)
            if edge is None:
                raise EdgeNotFoundError(f"Edge {command.edge_id} not found")

            edge.update(attributes=command.attributes)

            await repos.edges.save(edge)
            await self._uow.commit()
        return edge
