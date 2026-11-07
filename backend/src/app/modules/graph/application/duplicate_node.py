import copy
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.item_companions import ItemCompanions  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.graph.ports.edge_repository import EdgeRepository
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_EDGE_PAGE = 200


def _swap(end: uuid.UUID, source_id: uuid.UUID, node_id: uuid.UUID) -> uuid.UUID:
    """Return the copy's id where a connection end is the original, else the end."""
    return node_id if end == source_id else end


@dataclass(kw_only=True)
class DuplicateNodeCommand:
    """Request to copy an item under a new name.

    The fields and tags are always copied. Each flag adds one more thing from the
    original: its connections, its media (every attachment but the cover), its
    cover, and its manual collections.
    """

    node_id: uuid.UUID
    name: str
    copy_relationships: bool = field(default=False)
    copy_media: bool = field(default=False)
    copy_cover: bool = field(default=False)
    copy_collections: bool = field(default=False)


class DuplicateNode(CommandHandler[GraphUnitOfWork, DuplicateNodeCommand, Node]):
    """Create a new item from an existing one, owned by the caller.

    The copy has its own id and timestamps and is not a favourite. Media and
    collection membership live in other modules, so they are copied after the
    item commits: a failure there leaves the copy without them rather than
    undoing it.
    """

    access: ClassVar[Access] = Content(GraphPermission.ITEM_WRITE)

    def __init__(
        self, uow: GraphUnitOfWork, guard: AccessGuard, companions: ItemCompanions
    ) -> None:
        super().__init__(uow, guard)
        self._companions = companions

    async def _handle(self, command: DuplicateNodeCommand, actor: Actor) -> Node:
        """Copy the item and whatever else `command` asks for."""
        async with self._uow as repos:
            source = await repos.nodes.get(command.node_id, scope=self.scope(actor))
            if source is None:
                raise NodeNotFoundError(f"Node {command.node_id} not found")
            self._guard.assert_can_view(actor, source.owner_id)
            node = Node.create(
                owner_id=actor.id,
                name=command.name,
                type=source.type,
                description=source.description,
                attributes=copy.deepcopy(source.attributes),
                tags=list(source.tags),
                extra_schema=copy.deepcopy(source.extra_schema),
            )
            await repos.nodes.add(node)
            if command.copy_relationships:
                await self._copy_edges(repos.edges, source.id, node.id, actor)
            await self._uow.commit()
        if command.copy_media or command.copy_cover:
            await self._companions.copy_media(
                source.id,
                node.id,
                attachments=command.copy_media,
                cover=command.copy_cover,
                actor=actor,
            )
        if command.copy_collections:
            await self._companions.copy_collections(source.id, node.id, actor=actor)
        logger.info("node duplicated", node_id=node.id, source_id=source.id)
        return node

    async def _copy_edges(
        self,
        edges: EdgeRepository,
        source_id: uuid.UUID,
        node_id: uuid.UUID,
        actor: Actor,
    ) -> None:
        """Repeat each of the source's connections on the copy, same direction."""
        scope = self.scope(actor)
        after: uuid.UUID | None = None
        while page := await edges.list_for_node(
            source_id, scope=scope, after=after, limit=_EDGE_PAGE
        ):
            for edge in page:
                self._guard.assert_can_view(actor, edge.owner_id)
                await edges.add(
                    Edge.create(
                        owner_id=actor.id,
                        source_id=_swap(edge.source_id, source_id, node_id),
                        target_id=_swap(edge.target_id, source_id, node_id),
                        type=edge.type,
                        attributes=copy.deepcopy(edge.attributes),
                    )
                )
            after = page[-1].id
