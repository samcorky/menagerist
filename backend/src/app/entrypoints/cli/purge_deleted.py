"""Retention purge across modules, composed here, not by cross-module imports."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.modules.collections.application.purge_expired_collections import (
    PurgeExpiredCollections,
    PurgeExpiredCollectionsCommand,
)
from app.modules.graph.application.purge_expired_nodes import (
    PurgeExpiredNodes,
    PurgeExpiredNodesCommand,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class PurgeDeletedContentCommand:
    """Request to hard-delete everything deleted before `older_than`."""

    older_than: datetime
    dry_run: bool = False


@dataclass(frozen=True, kw_only=True)
class PurgeDeletedContentResult:
    """Counts per kind that were (or, for a dry run, would be) hard-deleted."""

    items: int
    connections: int
    collections: int


class PurgeDeletedContent:
    """Run the items-and-connections purge, then the collections purge.

    Each part is a `System` use case that checks the actor itself.
    """

    def __init__(
        self, nodes: PurgeExpiredNodes, collections: PurgeExpiredCollections
    ) -> None:
        self._nodes = nodes
        self._collections = collections

    async def handle(
        self, command: PurgeDeletedContentCommand, actor: Actor
    ) -> PurgeDeletedContentResult:
        """Purge (or count) every kind and sum the results."""
        nodes = await self._nodes.handle(
            PurgeExpiredNodesCommand(
                older_than=command.older_than, dry_run=command.dry_run
            ),
            actor,
        )
        collections = await self._collections.handle(
            PurgeExpiredCollectionsCommand(
                older_than=command.older_than, dry_run=command.dry_run
            ),
            actor,
        )
        return PurgeDeletedContentResult(
            items=nodes.items,
            connections=nodes.connections,
            collections=collections.collections,
        )


def build_purge_deleted_content_on(
    factory: async_sessionmaker[AsyncSession], storage: MediaStoragePort
) -> PurgeDeletedContent:
    """Compose the purge over Postgres sessions from `factory` and `storage`."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.entrypoints.api.shared.bridges.item_dependents import get_item_dependents
    from app.modules.collections.adapters.persistence.unit_of_work import (
        create_collections_uow,
    )
    from app.modules.graph.adapters.persistence.unit_of_work import create_graph_uow

    guard = get_access_guard()
    return PurgeDeletedContent(
        PurgeExpiredNodes(
            create_graph_uow(factory),
            guard,
            get_item_dependents(factory, storage, guard),
        ),
        PurgeExpiredCollections(create_collections_uow(factory), guard),
    )


def build_purge_deleted_content() -> PurgeDeletedContent:
    """Compose the purge over the instance database and local media storage."""
    from app.modules.media.adapters.storage.local_filesystem import (
        LocalFilesystemMediaStorage,
    )
    from app.platform.config.media import get_media_settings
    from app.platform.database import get_session_factory

    storage = LocalFilesystemMediaStorage(get_media_settings().storage_path)
    return build_purge_deleted_content_on(get_session_factory(), storage)
