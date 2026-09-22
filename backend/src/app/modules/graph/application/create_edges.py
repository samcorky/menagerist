import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_PAGE_SIZE = 100


@dataclass(kw_only=True)
class CreateEdgesCommand:
    """Request to connect one source node to several targets with the same type.

    Attributes apply to every created edge. A target already connected to the
    source by an edge of the same type is skipped, not duplicated.
    """

    source_id: uuid.UUID
    target_ids: list[uuid.UUID]
    type: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class CreateEdgesResult:
    """Edges created, and targets skipped because a matching edge already existed."""

    created: list[Edge]
    skipped: list[uuid.UUID]


async def _existing_targets(
    repos: GraphRepos, source_id: uuid.UUID, type_: str
) -> set[uuid.UUID]:
    """Ids connected to `source_id` by an edge of `type_`, either direction."""
    targets: set[uuid.UUID] = set()
    after: uuid.UUID | None = None
    while page := await repos.edges.list_for_node(
        source_id, after=after, limit=_PAGE_SIZE
    ):
        for edge in page:
            if edge.type == type_:
                targets.add(
                    edge.target_id if edge.source_id == source_id else edge.source_id
                )
        after = page[-1].id
    return targets


class CreateEdges(
    CommandHandler[GraphUnitOfWork, CreateEdgesCommand, CreateEdgesResult]
):
    """Create edges from one source to several targets in a single transaction."""

    async def handle(
        self, command: CreateEdgesCommand, actor: Actor
    ) -> CreateEdgesResult:
        """Create the edges in `command`, skipping targets already connected."""
        async with self._uow as repos:
            if await repos.nodes.get(command.source_id) is None:
                raise NodeNotFoundError(f"Node {command.source_id} not found")

            slug = slugify(command.type)
            edge_type = await repos.edge_types.get_by_slug(slug)
            if edge_type is None:
                await repos.edge_types.add(
                    EdgeType.create(
                        slug=slug, label=command.type.replace("-", " ").title()
                    )
                )
            elif edge_type.attributes_schema is not None:
                validate_attributes(edge_type.attributes_schema, command.attributes)

            existing = await _existing_targets(repos, command.source_id, command.type)

            created: list[Edge] = []
            skipped: list[uuid.UUID] = []
            for target_id in command.target_ids:
                if target_id in existing:
                    skipped.append(target_id)
                    continue
                if await repos.nodes.get(target_id) is None:
                    raise NodeNotFoundError(f"Node {target_id} not found")
                edge = Edge.create(
                    source_id=command.source_id,
                    target_id=target_id,
                    type=command.type,
                    attributes=command.attributes,
                )
                await repos.edges.add(edge)
                created.append(edge)
                existing.add(target_id)

            await self._uow.commit()
        logger.info(
            "edges created",
            source_id=command.source_id,
            created=len(created),
            skipped=len(skipped),
        )
        return CreateEdgesResult(created=created, skipped=skipped)
