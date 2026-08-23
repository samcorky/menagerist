from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class CreateNodeCommand:
    """Request to create a new node."""

    name: str
    type: str
    description: str | None = field(default=None)
    attributes: dict[str, Any] = field(default_factory=dict)


class CreateNode:
    """Create and persist a new node."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: CreateNodeCommand, actor: Actor) -> Node:
        """Create a node from `command` and commit it."""
        node = Node.create(
            name=command.name,
            type=command.type,
            description=command.description,
            attributes=command.attributes,
        )
        async with self._uow as repos:
            await repos.nodes.add(node)
            await self._uow.commit()
        return node
