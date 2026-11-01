from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.ports.item_dependents import ItemDependents  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

DEFAULT_BATCH_SIZE = 100


@dataclass(kw_only=True)
class PurgeExpiredNodesCommand:
    """Request to hard-delete content that was deleted before `older_than`."""

    older_than: datetime
    dry_run: bool = False
    batch_size: int = DEFAULT_BATCH_SIZE

    def __post_init__(self) -> None:
        """Refuse a naive cutoff or a batch that could never make progress."""
        if self.older_than.tzinfo is None:
            raise ValidationError("older_than must be timezone-aware")
        if self.batch_size < 1:
            raise ValidationError("batch_size must be at least 1")


@dataclass(frozen=True, kw_only=True)
class PurgeExpiredNodesResult:
    """How many rows were (or, for a dry run, would be) hard-deleted."""

    items: int
    connections: int


class PurgeExpiredNodes(
    CommandHandler[GraphUnitOfWork, PurgeExpiredNodesCommand, PurgeExpiredNodesResult]
):
    """Hard-delete every owner's items and connections deleted before the cutoff.

    Connections deleted on their own go first and are the ones counted; those
    touching a purged item go with it. Each item follows the same path as a
    person purging it: memberships and attachments (and the stored files only
    they used, after their commit), then its connections, then the item. Live
    rows are never touched, and a row restored since it was listed is skipped.
    A run that stops part-way leaves the rest to be purged next time.
    """

    access: ClassVar[Access] = System()

    def __init__(
        self, uow: GraphUnitOfWork, guard: AccessGuard, dependents: ItemDependents
    ) -> None:
        super().__init__(uow, guard)
        self._dependents = dependents

    async def _handle(
        self, command: PurgeExpiredNodesCommand, actor: Actor
    ) -> PurgeExpiredNodesResult:
        """Count (dry run) or purge connections, then items, in bounded batches."""
        if command.dry_run:
            async with self._uow as repos:
                return PurgeExpiredNodesResult(
                    items=await repos.nodes.count_deleted_before(command.older_than),
                    connections=await repos.edges.count_deleted_before(
                        command.older_than
                    ),
                )
        connections = await self._purge_connections(command)
        items = await self._purge_items(command)
        logger.info("expired content purged", items=items, connections=connections)
        return PurgeExpiredNodesResult(items=items, connections=connections)

    async def _purge_connections(self, command: PurgeExpiredNodesCommand) -> int:
        """Hard-delete connections deleted before the cutoff, batch by batch."""
        purged = 0
        while True:
            async with self._uow as repos:
                batch = await repos.edges.list_deleted_before(
                    command.older_than, limit=command.batch_size
                )
                for edge in batch:
                    await repos.edges.purge(edge.id)
                await self._uow.commit()
            if not batch:
                return purged
            purged += len(batch)

    async def _purge_items(self, command: PurgeExpiredNodesCommand) -> int:
        """Hard-delete items deleted before the cutoff, batch by batch."""
        purged = 0
        while True:
            async with self._uow as repos:
                batch = await repos.nodes.list_deleted_before(
                    command.older_than, limit=command.batch_size
                )
            if not batch:
                return purged
            for node in batch:
                if await self._purge_item(node.id, command.older_than):
                    purged += 1

    async def _purge_item(self, item_id: uuid.UUID, cutoff: datetime) -> bool:
        """Purge one item if it is still deleted before the cutoff."""
        async with self._uow as repos:
            node = await repos.nodes.get_deleted(
                item_id, scope=ContentFilter.everyone()
            )
            if node is None or not (node.deleted_at and node.deleted_at < cutoff):
                return False
            await self._dependents.purge_for_item(node.id)
            await repos.edges.purge_for_node(node.id)
            await repos.nodes.purge(node.id)
            await self._uow.commit()
        return True
