import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class UpdateEdgeTypeCommand:
    """Request to update an existing edge type."""

    edge_type_id: uuid.UUID
    label: str | None = field(default=None)
    reverse_label: str | None = field(default=None)
    description: str | None = field(default=None)
    directional: bool | None = field(default=None)
    attributes_schema: dict[str, Any] | None = field(default=None)


class UpdateEdgeType(CommandHandler[GraphUnitOfWork, UpdateEdgeTypeCommand, EdgeType]):
    """Apply partial updates to an existing edge type."""

    async def handle(self, command: UpdateEdgeTypeCommand, actor: Actor) -> EdgeType:
        """Apply the update and commit."""
        async with self._uow as repos:
            edge_type = await repos.edge_types.get(command.edge_type_id)
            if edge_type is None:
                raise EdgeTypeNotFoundError(
                    f"Edge type {command.edge_type_id} not found"
                )
            edge_type.update(
                label=command.label,
                reverse_label=command.reverse_label,
                description=command.description,
                directional=command.directional,
                attributes_schema=command.attributes_schema,
            )
            await repos.edge_types.save(edge_type)
            await self._uow.commit()
        return edge_type
