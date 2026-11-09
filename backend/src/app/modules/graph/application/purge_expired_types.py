from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.type_scope import owner_scope
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

DEFAULT_BATCH_SIZE = 100


@dataclass(kw_only=True)
class PurgeExpiredTypesCommand:
    """Request to hard-delete types that were deleted before `older_than`."""

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
class PurgeExpiredTypesResult:
    """How many types were (or, for a dry run, would be) hard-deleted."""

    item_types: int
    relationship_types: int


class PurgeExpiredTypes(
    CommandHandler[GraphUnitOfWork, PurgeExpiredTypesCommand, PurgeExpiredTypesResult]
):
    """Hard-delete item and relationship types deleted before the cutoff.

    Removing an example pack soft-deletes its types and nothing else removes them
    afterwards. A type is left alone while any item or connection, live or in
    Recently deleted, still carries its slug, unless a live type has since taken
    that slug over. Run this after the items and connections have been purged.
    """

    access: ClassVar[Access] = System()

    async def _handle(
        self, command: PurgeExpiredTypesCommand, actor: Actor
    ) -> PurgeExpiredTypesResult:
        """Count (dry run) or purge expired types in bounded batches."""
        item_types = await self._sweep_item_types(command)
        relationship_types = await self._sweep_relationship_types(command)
        logger.info(
            "expired types purged",
            item_types=item_types,
            relationship_types=relationship_types,
            dry_run=command.dry_run,
        )
        return PurgeExpiredTypesResult(
            item_types=item_types, relationship_types=relationship_types
        )

    async def _sweep_item_types(self, command: PurgeExpiredTypesCommand) -> int:
        """Walk the expired item types by id, so a type left in place is not retried."""
        swept = 0
        after = None
        while True:
            async with self._uow as repos:
                batch = await repos.node_types.list_deleted_before(
                    command.older_than, after=after, limit=command.batch_size
                )
            if not batch:
                return swept
            after = batch[-1].id
            for node_type in batch:
                async with self._uow as repos:
                    slug = str(node_type.slug)
                    owner = owner_scope(node_type.owner_id)
                    if (
                        await repos.nodes.has_any_of_type(slug, scope=owner)
                        and await repos.node_types.get_by_slug(slug, scope=owner)
                        is None
                    ):
                        continue
                    if not command.dry_run:
                        await repos.node_types.purge(node_type.id)
                        await self._uow.commit()
                swept += 1

    async def _sweep_relationship_types(self, command: PurgeExpiredTypesCommand) -> int:
        """Walk the expired relationship types by id, as for item types."""
        swept = 0
        after = None
        while True:
            async with self._uow as repos:
                batch = await repos.edge_types.list_deleted_before(
                    command.older_than, after=after, limit=command.batch_size
                )
            if not batch:
                return swept
            after = batch[-1].id
            for edge_type in batch:
                async with self._uow as repos:
                    slug = str(edge_type.slug)
                    owner = owner_scope(edge_type.owner_id)
                    if (
                        await repos.edges.has_any_of_type(slug, scope=owner)
                        and await repos.edge_types.get_by_slug(slug, scope=owner)
                        is None
                    ):
                        continue
                    if not command.dry_run:
                        await repos.edge_types.purge(edge_type.id)
                        await self._uow.commit()
                swept += 1
