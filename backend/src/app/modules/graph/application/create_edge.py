import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import NodeNotFoundError
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class CreateEdgeCommand:
    """Request to create a new edge between two node."""

    source_id: uuid.UUID
    target_id: uuid.UUID
    type: str
    attributes: dict[str, Any] = field(default_factory=dict)


class CreateEdge:
    """Create and persist a new edge, auto-creating its EdgeType if not yet known."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: CreateEdgeCommand, actor: Actor) -> Edge:
        """Create an edge from `command` and commit it.

        If no EdgeType exists for the given type slug, one is created automatically
        so the vocabulary builds itself as edges are added.
        """
        async with self._uow as repos:
            if await repos.nodes.get(command.source_id) is None:
                raise NodeNotFoundError(f"Node {command.source_id} not found")
            if await repos.nodes.get(command.target_id) is None:
                raise NodeNotFoundError(f"Node {command.target_id} not found")

            slug = slugify(command.type)
            if await repos.edge_types.get_by_slug(slug) is None:
                await repos.edge_types.add(
                    EdgeType.create(
                        slug=slug,
                        label=command.type.replace("-", " ").title(),
                    )
                )

            edge = Edge.create(
                source_id=command.source_id,
                target_id=command.target_id,
                type=command.type,
                attributes=command.attributes,
            )
            await repos.edges.add(edge)
            await self._uow.commit()
        return edge
