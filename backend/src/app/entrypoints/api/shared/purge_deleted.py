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
from app.modules.graph.application.purge_expired_types import (
    PurgeExpiredTypes,
    PurgeExpiredTypesCommand,
)
from app.modules.presets.application.purge_expired_presets import (
    PurgeExpiredPresets,
    PurgeExpiredPresetsCommand,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
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
    item_types: int = 0
    relationship_types: int = 0
    presets: int = 0


class PurgeDeletedContent:
    """Run the items-and-connections, collections, types and presets purges.

    The order matters: types wait for the items that carry them, and presets for
    the types that link to them. Each part is a `System` use case that checks the
    actor itself.
    """

    def __init__(
        self,
        nodes: PurgeExpiredNodes,
        collections: PurgeExpiredCollections,
        types: PurgeExpiredTypes,
        presets: PurgeExpiredPresets,
    ) -> None:
        self._nodes = nodes
        self._collections = collections
        self._types = types
        self._presets = presets

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
        types = await self._types.handle(
            PurgeExpiredTypesCommand(
                older_than=command.older_than, dry_run=command.dry_run
            ),
            actor,
        )
        presets = await self._presets.handle(
            PurgeExpiredPresetsCommand(
                older_than=command.older_than, dry_run=command.dry_run
            ),
            actor,
        )
        return PurgeDeletedContentResult(
            items=nodes.items,
            connections=nodes.connections,
            collections=collections.collections,
            item_types=types.item_types,
            relationship_types=types.relationship_types,
            presets=presets.presets,
        )


class _GraphPresetUsage:
    """Preset usage read from a fresh graph transaction on each question."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def types_using(self, preset_id: uuid.UUID) -> list[str]:
        """Return the labels of the live types that link to `preset_id`."""
        from app.entrypoints.api.shared.bridges.preset_usage import GraphPresetUsage

        async with self._uow as repos:
            return await GraphPresetUsage(repos).types_using(preset_id)


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
    from app.modules.presets.adapters.persistence.unit_of_work import create_preset_uow

    guard = get_access_guard()
    return PurgeDeletedContent(
        PurgeExpiredNodes(
            create_graph_uow(factory),
            guard,
            get_item_dependents(factory, storage, guard),
        ),
        PurgeExpiredCollections(create_collections_uow(factory), guard),
        PurgeExpiredTypes(create_graph_uow(factory), guard),
        PurgeExpiredPresets(
            create_preset_uow(factory),
            guard,
            _GraphPresetUsage(create_graph_uow(factory)),
        ),
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
