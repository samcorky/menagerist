import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import EdgeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateEdgeCommand:
    """Request to update an edge's editable fields.

    `attributes` left as `None` is unchanged - `source_id`/`target_id`/`type`
    aren't editable.
    """

    edge_id: uuid.UUID
    attributes: dict[str, Any] | None = field(default=None)


class UpdateEdge(CommandHandler[GraphUnitOfWork, UpdateEdgeCommand, Edge]):
    """Update an existing edge's editable fields."""

    async def handle(self, command: UpdateEdgeCommand, actor: Actor) -> Edge:
        """Apply `command`'s changes to the edge and commit."""
        async with self._uow as repos:
            edge = await repos.edges.get(command.edge_id)
            if edge is None:
                raise EdgeNotFoundError(f"Edge {command.edge_id} not found")

            if command.attributes is not None:
                edge_type = await repos.edge_types.get_by_slug(slugify(edge.type))
                if edge_type is not None and edge_type.attributes_schema is not None:
                    validate_attributes(
                        edge_type.attributes_schema,
                        command.attributes,
                        previous=edge.attributes,
                    )

            edge.update(attributes=command.attributes)

            await repos.edges.save(edge)
            await self._uow.commit()
        logger.info("edge updated", edge_id=command.edge_id)
        return edge
