from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.errors import NodeTypeSlugConflictError
from app.modules.graph.domain.node_type import NodeType

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class CreateNodeTypeCommand:
    """Request to create a new node type."""

    slug: str
    label: str
    description: str | None = field(default=None)
    attributes_schema: dict[str, Any] | None = field(default=None)


class CreateNodeType:
    """Create and persist a new node type."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: CreateNodeTypeCommand, actor: Actor) -> NodeType:
        """Create a node type from `command` and commit it."""
        async with self._uow as repos:
            if await repos.node_types.get_by_slug(command.slug) is not None:
                raise NodeTypeSlugConflictError(
                    f"NodeType with slug '{command.slug}' already exists"
                )
            node_type = NodeType.create(
                slug=command.slug,
                label=command.label,
                description=command.description,
                attributes_schema=command.attributes_schema,
            )
            await repos.node_types.add(node_type)
            await self._uow.commit()
        return node_type
