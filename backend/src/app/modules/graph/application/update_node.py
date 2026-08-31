import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class UpdateNodeCommand:
    """Request to update a node's editable fields.

    A field left as `None` is unchanged. `type` is one-time-settable — it can
    be assigned when currently `None` but cannot be changed once set.
    """

    node_id: uuid.UUID
    name: str | None = field(default=None)
    type: str | None = field(default=None)
    description: str | None = field(default=None)
    attributes: dict[str, Any] | None = field(default=None)


class UpdateNode:
    """Update an existing node's editable fields."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: UpdateNodeCommand, actor: Actor) -> Node:
        """Apply `command`'s changes to the node and commit."""
        async with self._uow as repos:
            node = await repos.nodes.get(command.node_id)
            if node is None:
                raise NodeNotFoundError(f"Node {command.node_id} not found")

            node.update(
                name=command.name,
                type=command.type,
                description=command.description,
                attributes=command.attributes,
            )

            if command.type is not None:
                slug = slugify(command.type)
                if await repos.node_types.get_by_slug(slug) is None:
                    await repos.node_types.add(
                        NodeType.create(slug=slug, label=command.type)
                    )

            await repos.nodes.save(node)
            await self._uow.commit()
        return node
