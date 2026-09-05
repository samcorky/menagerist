import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class UpdateNodeTypeCommand:
    """Request to update a node type's editable fields. `slug` is immutable."""

    node_type_id: uuid.UUID
    label: str | None = field(default=None)
    description: str | None = field(default=None)
    attributes_schema: dict[str, Any] | None = field(default=None)


class UpdateNodeType(CommandHandler[GraphUnitOfWork, UpdateNodeTypeCommand, NodeType]):
    """Update an existing node type's editable fields."""

    async def handle(self, command: UpdateNodeTypeCommand, actor: Actor) -> NodeType:
        """Apply `command`'s changes to the node type and commit."""
        async with self._uow as repos:
            node_type = await repos.node_types.get(command.node_type_id)
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )

            node_type.update(
                label=command.label,
                description=command.description,
                attributes_schema=command.attributes_schema,
            )

            await repos.node_types.save(node_type)
            await self._uow.commit()
        return node_type
