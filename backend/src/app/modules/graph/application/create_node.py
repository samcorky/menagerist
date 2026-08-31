from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class CreateNodeCommand:
    """Request to create a new node."""

    name: str
    type: str | None = field(default=None)
    description: str | None = field(default=None)
    attributes: dict[str, Any] = field(default_factory=dict)


class CreateNode:
    """Create and persist a new node, auto-creating its NodeType if not yet known."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: CreateNodeCommand, actor: Actor) -> Node:
        """Create a node from `command` and commit it.

        If no NodeType exists for the given type slug, one is created automatically
        so the vocabulary builds itself as nodes are added.
        """
        node = Node.create(
            name=command.name,
            type=command.type,
            description=command.description,
            attributes=command.attributes,
        )
        async with self._uow as repos:
            if command.type is not None:
                slug = slugify(command.type)
                if await repos.node_types.get_by_slug(slug) is None:
                    await repos.node_types.add(
                        NodeType.create(slug=slug, label=command.type)
                    )
            await repos.nodes.add(node)
            await self._uow.commit()
        return node
