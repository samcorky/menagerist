import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.application.choice_lists import resolve_choice_lists
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import NodeNotFoundError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.access import Access, Content

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.content_filter import ContentFilter  # noqa: TC001
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
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
    repos: GraphRepos, source_id: uuid.UUID, type_: str, scope: ContentFilter
) -> set[uuid.UUID]:
    """Ids connected to `source_id` by an edge of `type_`, either direction."""
    targets: set[uuid.UUID] = set()
    after: uuid.UUID | None = None
    while page := await repos.edges.list_for_node(
        source_id, scope=scope, after=after, limit=_PAGE_SIZE
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

    access: ClassVar[Access] = Content(GraphPermission.ITEM_WRITE)

    def __init__(
        self,
        uow: GraphUnitOfWork,
        guard: AccessGuard,
        choice_lists: ChoiceListSource | None = None,
    ) -> None:
        super().__init__(uow, guard)
        self._choice_lists = choice_lists

    async def _handle(
        self, command: CreateEdgesCommand, actor: Actor
    ) -> CreateEdgesResult:
        """Create the edges in `command`, skipping targets already connected."""
        scope = self.scope(actor)
        async with self._uow as repos:
            if await repos.nodes.get(command.source_id, scope=scope) is None:
                raise NodeNotFoundError(f"Node {command.source_id} not found")

            existing = await _existing_targets(
                repos, command.source_id, command.type, scope
            )

            # Check every endpoint before writing, so a bad one creates nothing.
            for target_id in command.target_ids:
                if (
                    target_id not in existing
                    and await repos.nodes.get(target_id, scope=scope) is None
                ):
                    raise NodeNotFoundError(f"Node {target_id} not found")

            slug = slugify(command.type)
            edge_type = await repos.edge_types.get_by_slug(slug)
            if edge_type is None:
                await repos.edge_types.add(
                    EdgeType.create(
                        slug=slug, label=command.type.replace("-", " ").title()
                    )
                )
            elif edge_type.attributes_schema is not None:
                schema = await resolve_choice_lists(
                    edge_type.attributes_schema, self._choice_lists
                )
                validate_attributes(schema, command.attributes)

            created: list[Edge] = []
            skipped: list[uuid.UUID] = []
            for target_id in command.target_ids:
                if target_id in existing:
                    skipped.append(target_id)
                    continue
                edge = Edge.create(
                    owner_id=actor.id,
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
