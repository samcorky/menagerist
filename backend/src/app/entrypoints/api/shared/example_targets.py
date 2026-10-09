"""Adapters that let the examples module drive the graph and presets use cases."""

import copy
import hashlib
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.entrypoints.api.shared.choice_list_source import PresetChoiceListSource
from app.entrypoints.api.shared.collection_items import GraphItemLookup
from app.entrypoints.api.shared.preset_usage import GraphPresetUsage
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
    create_collections_uow,
    create_in_memory_collections_uow,
)
from app.modules.collections.application.add_items_to_collection import (
    AddItemsToCollection,
    AddItemsToCollectionCommand,
)
from app.modules.collections.application.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from app.modules.collections.application.delete_collection import (
    DeleteCollection,
    DeleteCollectionCommand,
)
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.item_lookup import ItemLookup
from app.modules.collections.ports.unit_of_work import (
    CollectionsRepos,
    CollectionsUnitOfWork,
)
from app.modules.examples.adapters.covers.pillow_cover_renderer import (
    PillowCoverRenderer,
)
from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import (
    PackCollection,
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
    resolve_preset_refs,
)
from app.modules.examples.ports.pack_targets import (
    Created,
    Inspection,
    PresetOutcome,
    RemoveResult,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_graph_repos,
    create_graph_uow,
    create_in_memory_graph_uow,
)
from app.modules.graph.application.create_edge import CreateEdge, CreateEdgeCommand
from app.modules.graph.application.create_edge_type import (
    CreateEdgeType,
    CreateEdgeTypeCommand,
)
from app.modules.graph.application.create_node import CreateNode, CreateNodeCommand
from app.modules.graph.application.create_node_type import (
    CreateNodeType,
    CreateNodeTypeCommand,
)
from app.modules.graph.application.delete_edge import DeleteEdge, DeleteEdgeCommand
from app.modules.graph.application.delete_edge_type import (
    DeleteEdgeType,
    DeleteEdgeTypeCommand,
)
from app.modules.graph.application.delete_node import DeleteNode, DeleteNodeCommand
from app.modules.graph.application.delete_node_type import (
    DeleteNodeType,
    DeleteNodeTypeCommand,
)
from app.modules.graph.domain.edge import Edge  # noqa: TC001
from app.modules.graph.domain.edge_type import EdgeType  # noqa: TC001
from app.modules.graph.domain.errors import (
    EdgeNotFoundError,
    EdgeTypeInUseError,
    EdgeTypeNotFoundError,
    NodeNotFoundError,
    NodeTypeNotFoundError,
)
from app.modules.graph.domain.node import Node  # noqa: TC001
from app.modules.graph.domain.node_type import NodeType  # noqa: TC001
from app.modules.graph.ports.choice_list_source import ChoiceListSource
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.modules.media.adapters.api.dependencies import (
    get_attachment_policy,
    get_image_processor,
    get_media_storage,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    build_media_repos,
    create_in_memory_media_uow,
    create_media_uow,
)
from app.modules.media.application.delete_media import DeleteMedia, DeleteMediaCommand
from app.modules.media.application.detach_media import DetachMedia, DetachMediaCommand
from app.modules.media.application.set_media_cover import (
    SetMediaCover,
    SetMediaCoverCommand,
)
from app.modules.media.application.upload_and_attach_media import (
    UploadAndAttachMedia,
    UploadAndAttachMediaCommand,
)
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.media_attachment import AttachmentKey, AttachmentTarget
from app.modules.media.ports.attachment_policy import (
    AttachmentPolicyPort,  # noqa: TC001
)
from app.modules.media.ports.image_processor import ImageProcessorPort  # noqa: TC001
from app.modules.media.ports.media_storage import MediaStoragePort  # noqa: TC001
from app.modules.media.ports.unit_of_work import MediaRepos, MediaUnitOfWork
from app.modules.presets.adapters.persistence.unit_of_work import (
    build_preset_repos,
    create_in_memory_preset_uow,
    create_preset_uow,
)
from app.modules.presets.application.delete_preset import (
    DeletePreset,
    DeletePresetCommand,
)
from app.modules.presets.application.import_presets import (
    ImportPresets,
    ImportPresetsCommand,
)
from app.modules.presets.application.pack import PACK_FORMAT, PACK_VERSION
from app.modules.presets.domain.errors import (
    BuiltinPresetError,
    PresetInUseError,
    PresetNotFoundError,
)
from app.modules.presets.domain.preset import Preset  # noqa: TC001
from app.modules.presets.ports.preset_usage import PresetUsage
from app.modules.presets.ports.unit_of_work import PresetRepos, PresetUnitOfWork
from app.platform.database import get_session_factory
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.examples.ports.cover_renderer import CoverRenderer

_PAGE = 1
_GRAPH_KINDS = frozenset(
    {
        EntityKind.ITEM,
        EntityKind.ITEM_TYPE,
        EntityKind.RELATIONSHIP_TYPE,
        EntityKind.CONNECTION,
    }
)


# ---- stores: how targets reach storage (sessions in production, memory in tests) ----


@dataclass(kw_only=True)
class PresetStores:
    """Factories the preset target uses; each call opens fresh storage access."""

    uow: Callable[[], PresetUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[PresetRepos]]
    usage: Callable[[], AbstractAsyncContextManager[PresetUsage]]


@dataclass(kw_only=True)
class GraphStores:
    """Factories the graph target uses; each call opens fresh storage access."""

    uow: Callable[[], GraphUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[GraphRepos]]
    media: Callable[[], AbstractAsyncContextManager[MediaRepos]]
    choice_lists: Callable[[], AbstractAsyncContextManager[ChoiceListSource]]
    collections: Callable[[], AbstractAsyncContextManager[CollectionsRepos]]


@dataclass(kw_only=True)
class CollectionStores:
    """Factories the collection target uses; each call opens fresh storage access."""

    uow: Callable[[], CollectionsUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[CollectionsRepos]]
    items: Callable[[], AbstractAsyncContextManager[ItemLookup]]


@dataclass(kw_only=True)
class CoverStores:
    """Factories the cover target uses; each call opens fresh storage access."""

    uow: Callable[[], MediaUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[MediaRepos]]


def build_in_memory_collections_repos() -> CollectionsRepos:
    """Return empty in-memory collections repositories, for tests."""
    return CollectionsRepos(
        collections=InMemoryCollectionRepository(),
        memberships=InMemoryMembershipRepository(),
    )


def in_memory_preset_stores(
    preset_repos: PresetRepos, graph_repos: GraphRepos
) -> PresetStores:
    """Stores over in-memory repositories, for tests."""

    @asynccontextmanager
    async def read() -> AsyncIterator[PresetRepos]:
        yield preset_repos

    @asynccontextmanager
    async def usage() -> AsyncIterator[PresetUsage]:
        yield GraphPresetUsage(graph_repos)

    return PresetStores(
        uow=lambda: create_in_memory_preset_uow(preset_repos), read=read, usage=usage
    )


def in_memory_graph_stores(
    graph_repos: GraphRepos,
    media_repos: MediaRepos,
    preset_repos: PresetRepos,
    collection_repos: CollectionsRepos | None = None,
) -> GraphStores:
    """Stores over in-memory repositories, for tests."""
    collection_repos = collection_repos or build_in_memory_collections_repos()

    @asynccontextmanager
    async def read() -> AsyncIterator[GraphRepos]:
        yield graph_repos

    @asynccontextmanager
    async def media() -> AsyncIterator[MediaRepos]:
        yield media_repos

    @asynccontextmanager
    async def choice_lists() -> AsyncIterator[ChoiceListSource]:
        yield PresetChoiceListSource(preset_repos)

    @asynccontextmanager
    async def collections() -> AsyncIterator[CollectionsRepos]:
        yield collection_repos

    return GraphStores(
        uow=lambda: create_in_memory_graph_uow(graph_repos),
        read=read,
        media=media,
        choice_lists=choice_lists,
        collections=collections,
    )


def in_memory_collection_stores(
    collection_repos: CollectionsRepos, graph_repos: GraphRepos
) -> CollectionStores:
    """Stores over in-memory repositories, for tests."""

    @asynccontextmanager
    async def read() -> AsyncIterator[CollectionsRepos]:
        yield collection_repos

    @asynccontextmanager
    async def items() -> AsyncIterator[ItemLookup]:
        yield GraphItemLookup(graph_repos)

    return CollectionStores(
        uow=lambda: create_in_memory_collections_uow(collection_repos),
        read=read,
        items=items,
    )


def in_memory_cover_stores(media_repos: MediaRepos) -> CoverStores:
    """Stores over in-memory repositories, for tests."""

    @asynccontextmanager
    async def read() -> AsyncIterator[MediaRepos]:
        yield media_repos

    return CoverStores(uow=lambda: create_in_memory_media_uow(media_repos), read=read)


def build_preset_stores(
    session_factory: async_sessionmaker[AsyncSession],
) -> PresetStores:
    """Stores over Postgres sessions."""

    @asynccontextmanager
    async def read() -> AsyncIterator[PresetRepos]:
        async with session_factory() as session:
            yield build_preset_repos(session)

    @asynccontextmanager
    async def usage() -> AsyncIterator[PresetUsage]:
        async with session_factory() as session:
            yield GraphPresetUsage(build_graph_repos(session))

    return PresetStores(
        uow=lambda: create_preset_uow(session_factory), read=read, usage=usage
    )


def build_graph_stores(
    session_factory: async_sessionmaker[AsyncSession],
) -> GraphStores:
    """Stores over Postgres sessions."""

    @asynccontextmanager
    async def read() -> AsyncIterator[GraphRepos]:
        async with session_factory() as session:
            yield build_graph_repos(session)

    @asynccontextmanager
    async def media() -> AsyncIterator[MediaRepos]:
        async with session_factory() as session:
            yield build_media_repos(session)

    @asynccontextmanager
    async def choice_lists() -> AsyncIterator[ChoiceListSource]:
        async with session_factory() as session:
            yield PresetChoiceListSource(build_preset_repos(session))

    @asynccontextmanager
    async def collections() -> AsyncIterator[CollectionsRepos]:
        async with session_factory() as session:
            yield build_collections_repos(session)

    return GraphStores(
        uow=lambda: create_graph_uow(session_factory),
        read=read,
        media=media,
        choice_lists=choice_lists,
        collections=collections,
    )


def build_collection_stores(
    session_factory: async_sessionmaker[AsyncSession],
) -> CollectionStores:
    """Stores over Postgres sessions."""

    @asynccontextmanager
    async def read() -> AsyncIterator[CollectionsRepos]:
        async with session_factory() as session:
            yield build_collections_repos(session)

    @asynccontextmanager
    async def items() -> AsyncIterator[ItemLookup]:
        async with session_factory() as session:
            yield GraphItemLookup(build_graph_repos(session))

    return CollectionStores(
        uow=lambda: create_collections_uow(session_factory),
        read=read,
        items=items,
    )


def build_cover_stores(
    session_factory: async_sessionmaker[AsyncSession],
) -> CoverStores:
    """Stores over Postgres sessions."""

    @asynccontextmanager
    async def read() -> AsyncIterator[MediaRepos]:
        async with session_factory() as session:
            yield build_media_repos(session)

    return CoverStores(uow=lambda: create_media_uow(session_factory), read=read)


# ---- content: what the pack defines, read back from what was stored ----


def _preset_content(p: Preset) -> dict[str, Any]:
    return {
        "kind": p.kind,
        "label": p.label,
        "description": p.description,
        "definition": copy.deepcopy(p.definition),
    }


def _node_type_content(t: NodeType) -> dict[str, Any]:
    return {
        "slug": str(t.slug),
        "label": t.label,
        "description": t.description,
        "attributes_schema": copy.deepcopy(t.attributes_schema),
    }


def _edge_type_content(t: EdgeType) -> dict[str, Any]:
    return {
        "slug": str(t.slug),
        "label": t.label,
        "reverse_label": t.reverse_label,
        "description": t.description,
        "directional": t.directional,
        "attributes_schema": copy.deepcopy(t.attributes_schema),
    }


def _node_content(n: Node) -> dict[str, Any]:
    # `favourite` is left out on purpose: starring an example is not editing it.
    return {
        "name": n.name,
        "type": n.type,
        "description": n.description,
        "attributes": copy.deepcopy(n.attributes),
        "tags": list(n.tags),
        "extra_schema": copy.deepcopy(n.extra_schema),
    }


def _edge_content(e: Edge) -> dict[str, Any]:
    return {
        "source_id": str(e.source_id),
        "target_id": str(e.target_id),
        "type": e.type,
        "attributes": copy.deepcopy(e.attributes),
    }


def _collection_content(
    name: str, description: str | None, members: Sequence[uuid.UUID]
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "members": sorted(str(m) for m in members),
    }


# A cover's file is named "<item name> (<style>).png", which is how `inspect`
# recovers name and style: the media module stores nothing else about it.
_COVER_FILENAME = re.compile(r"(?P<name>.*) \((?P<style>[a-z]+)\)\.png", re.DOTALL)


def _cover_filename(name: str, style: str) -> str:
    return f"{name} ({style}).png"


def _cover_content(
    name: str | None, style: str | None, sha256: str | None
) -> dict[str, Any]:
    return {"style": style, "name": name, "sha256": sha256}


async def _single_chunk(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _resolved(
    schema: dict[str, Any] | None, presets: Mapping[str, uuid.UUID]
) -> dict[str, Any] | None:
    if schema is None:
        return None
    result: dict[str, Any] = resolve_preset_refs(
        schema, {k: str(v) for k, v in presets.items()}
    )
    return result


# ---- the targets ----


class PresetPackTarget:
    """Implements `PresetTarget` with the presets use cases."""

    def __init__(self, stores: PresetStores) -> None:
        self._stores = stores

    async def ensure(self, presets: Sequence[PackPreset]) -> list[PresetOutcome]:
        """Create each preset unless an identical one exists."""
        if not presets:
            return []
        command = ImportPresetsCommand(
            pack_format=PACK_FORMAT,
            pack_version=PACK_VERSION,
            items=[
                {
                    "kind": p.kind,
                    "label": p.label,
                    "description": p.description,
                    "definition": copy.deepcopy(p.definition),
                }
                for p in presets
            ],
        )
        result = await ImportPresets(self._stores.uow()).handle(command, SYSTEM_ACTOR)
        # Built from the spec: the import stores these fields unchanged, and a
        # read-back failing here would leave committed presets unrecorded.
        return [
            PresetOutcome(
                ref=spec.ref,
                entity_id=imported.id,
                created=imported.created,
                content={
                    "kind": spec.kind,
                    "label": spec.label,
                    "description": spec.description,
                    "definition": copy.deepcopy(spec.definition),
                },
            )
            for spec, imported in zip(presets, result.items, strict=True)
        ]

    async def inspect(self, preset_id: uuid.UUID) -> Inspection | None:
        """Return the preset as it is now, or `None` if it is gone."""
        async with self._stores.read() as repos:
            preset = await repos.presets.get(preset_id)
        return None if preset is None else Inspection(content=_preset_content(preset))

    async def remove(self, preset_id: uuid.UUID) -> RemoveResult:
        """Remove the preset unless it is built in or an item type still uses it."""
        async with self._stores.usage() as usage:
            try:
                await DeletePreset(self._stores.uow(), usage).handle(
                    DeletePresetCommand(preset_id=preset_id), SYSTEM_ACTOR
                )
            except PresetInUseError, BuiltinPresetError:
                return RemoveResult.REFUSED_IN_USE
            except PresetNotFoundError:
                return RemoveResult.ALREADY_GONE
        return RemoveResult.REMOVED


class GraphPackTarget:
    """Implements `GraphTarget` with the graph use cases."""

    def __init__(self, stores: GraphStores) -> None:
        self._stores = stores

    async def slug_taken(self, kind: EntityKind, slug: str) -> bool:
        """Whether a live type of `kind` already has `slug`."""
        async with self._stores.read() as repos:
            # Pack slugs are already normalised; edge types normalise on create.
            if kind is EntityKind.ITEM_TYPE:
                return await repos.node_types.get_by_slug(slug) is not None
            return await repos.edge_types.get_by_slug(slugify(slug)) is not None

    async def create_relationship_type(
        self, spec: PackRelationshipType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the relationship type."""
        command = CreateEdgeTypeCommand(
            slug=spec.slug,
            label=spec.label,
            reverse_label=spec.reverse_label,
            description=spec.description,
            directional=spec.directional,
            attributes_schema=_resolved(spec.attributes_schema, presets),
        )
        async with self._stores.choice_lists() as source:
            edge_type = await CreateEdgeType(self._stores.uow(), source).handle(
                command, SYSTEM_ACTOR
            )
        return Created(entity_id=edge_type.id, content=_edge_type_content(edge_type))

    async def create_item_type(
        self, spec: PackItemType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the item type."""
        command = CreateNodeTypeCommand(
            slug=spec.slug,
            label=spec.label,
            description=spec.description,
            attributes_schema=_resolved(spec.attributes_schema, presets),
        )
        async with self._stores.choice_lists() as source:
            node_type = await CreateNodeType(self._stores.uow(), source).handle(
                command, SYSTEM_ACTOR
            )
        return Created(entity_id=node_type.id, content=_node_type_content(node_type))

    async def create_item(self, spec: PackItem, *, type_slug: str) -> Created:
        """Create the item under `type_slug`."""
        command = CreateNodeCommand(
            name=spec.name,
            type=type_slug,
            description=spec.description,
            attributes=spec.attributes,
            tags=list(spec.tags),
            extra_schema=spec.extra_schema,
        )
        async with self._stores.choice_lists() as source:
            node = await CreateNode(self._stores.uow(), source).handle(
                command, SYSTEM_ACTOR
            )
        return Created(entity_id=node.id, content=_node_content(node))

    async def create_connection(
        self,
        spec: PackConnection,
        *,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        type_slug: str,
    ) -> Created:
        """Create the connection."""
        command = CreateEdgeCommand(
            source_id=source_id,
            target_id=target_id,
            type=type_slug,
            attributes=spec.attributes,
        )
        async with self._stores.choice_lists() as source:
            edge = await CreateEdge(self._stores.uow(), source).handle(
                command, SYSTEM_ACTOR
            )
        return Created(entity_id=edge.id, content=_edge_content(edge))

    async def inspect(
        self, kind: EntityKind, entity_id: uuid.UUID
    ) -> Inspection | None:
        """Return the entity as it is now, or `None` if it is gone."""
        async with self._stores.read() as repos:
            if kind is EntityKind.ITEM:
                return await self._inspect_item(repos, entity_id)
            if kind is EntityKind.ITEM_TYPE:
                return await self._inspect_item_type(repos, entity_id)
            if kind is EntityKind.RELATIONSHIP_TYPE:
                return await self._inspect_relationship_type(repos, entity_id)
            if kind is EntityKind.CONNECTION:
                edge = await repos.edges.get(entity_id)
                return None if edge is None else Inspection(content=_edge_content(edge))
        raise ValueError(f"The graph target does not handle {kind.value} entities")

    async def _inspect_item(
        self, repos: GraphRepos, entity_id: uuid.UUID
    ) -> Inspection | None:
        node = await repos.nodes.get(entity_id)
        if node is None:
            return None
        touched = await repos.edges.list_for_node(node.id, after=None, limit=_PAGE)
        async with self._stores.media() as media:
            files = await media.attachments.list_for_target(
                AttachmentTarget.NODE, node.id
            )
        in_collection = await self._on_live_collection(node.id)
        return Inspection(
            content=_node_content(node),
            has_user_data=bool(touched or files or in_collection),
        )

    async def _on_live_collection(self, item_id: uuid.UUID) -> bool:
        """Whether any live collection holds the item."""
        async with self._stores.collections() as repos:
            for collection_id in await repos.memberships.collection_ids_for(item_id):
                if await repos.collections.get(collection_id) is not None:
                    return True
        return False

    @staticmethod
    async def _inspect_item_type(
        repos: GraphRepos, entity_id: uuid.UUID
    ) -> Inspection | None:
        node_type = await repos.node_types.get(entity_id)
        if node_type is None:
            return None
        items = await repos.nodes.list(
            after=None, limit=_PAGE, type=str(node_type.slug)
        )
        return Inspection(
            content=_node_type_content(node_type), still_in_use=bool(items)
        )

    @staticmethod
    async def _inspect_relationship_type(
        repos: GraphRepos, entity_id: uuid.UUID
    ) -> Inspection | None:
        edge_type = await repos.edge_types.get(entity_id)
        if edge_type is None:
            return None
        in_use = await repos.edges.has_edges_of_type(str(edge_type.slug))
        return Inspection(content=_edge_type_content(edge_type), still_in_use=in_use)

    async def remove(self, kind: EntityKind, entity_id: uuid.UUID) -> RemoveResult:
        """Remove the entity through its delete use case."""
        if kind not in _GRAPH_KINDS:
            raise ValueError(f"The graph target does not handle {kind.value} entities")
        uow = self._stores.uow()
        try:
            if kind is EntityKind.ITEM:
                await DeleteNode(uow).handle(
                    DeleteNodeCommand(node_id=entity_id), SYSTEM_ACTOR
                )
            elif kind is EntityKind.ITEM_TYPE:
                await DeleteNodeType(uow).handle(
                    DeleteNodeTypeCommand(node_type_id=entity_id), SYSTEM_ACTOR
                )
            elif kind is EntityKind.RELATIONSHIP_TYPE:
                await DeleteEdgeType(uow).handle(
                    DeleteEdgeTypeCommand(edge_type_id=entity_id), SYSTEM_ACTOR
                )
            else:
                await DeleteEdge(uow).handle(
                    DeleteEdgeCommand(edge_id=entity_id), SYSTEM_ACTOR
                )
        except (
            NodeNotFoundError,
            NodeTypeNotFoundError,
            EdgeTypeNotFoundError,
            EdgeNotFoundError,
        ):
            return RemoveResult.ALREADY_GONE
        except EdgeTypeInUseError:
            return RemoveResult.REFUSED_IN_USE
        return RemoveResult.REMOVED


class CollectionPackTarget:
    """Implements `CollectionTarget` with the collections use cases."""

    def __init__(self, stores: CollectionStores) -> None:
        self._stores = stores

    async def create_collection(
        self, spec: PackCollection, *, item_ids: Sequence[uuid.UUID]
    ) -> Created:
        """Create the collection, put the items on it and return what was stored."""
        collection = await CreateCollection(self._stores.uow()).handle(
            CreateCollectionCommand(name=spec.name, description=spec.description),
            SYSTEM_ACTOR,
        )
        try:
            async with self._stores.items() as items:
                await AddItemsToCollection(self._stores.uow(), items).handle(
                    AddItemsToCollectionCommand(
                        collection_id=collection.id, item_ids=list(item_ids)
                    ),
                    SYSTEM_ACTOR,
                )
            inspection = await self.inspect(collection.id)
        except Exception:
            # Not yet recorded by the install, so it would be orphaned.
            await self.remove(collection.id)
            raise
        if inspection is None:  # pragma: no cover - only if deleted concurrently
            raise RuntimeError(f"Collection {collection.id} vanished after creation")
        return Created(entity_id=collection.id, content=inspection.content)

    async def inspect(self, collection_id: uuid.UUID) -> Inspection | None:
        """Return the collection as it is now, or `None` if it is gone.

        Members are the stored memberships whose items are still live, as the
        collection page shows them, so a deleted item reads as a membership change.
        """
        async with self._stores.read() as repos, self._stores.items() as items:
            collection = await repos.collections.get(collection_id)
            if collection is None:
                return None
            stored = await repos.memberships.item_ids(collection_id)
            live = await items.live_ids(list(stored))
        return Inspection(
            content=_collection_content(
                collection.name, collection.description, list(live)
            )
        )

    async def remove(self, collection_id: uuid.UUID) -> RemoveResult:
        """Soft-delete the collection through its delete use case."""
        try:
            await DeleteCollection(self._stores.uow()).handle(
                DeleteCollectionCommand(collection_id=collection_id), SYSTEM_ACTOR
            )
        except CollectionNotFoundError:
            return RemoveResult.ALREADY_GONE
        return RemoveResult.REMOVED


class CoverPackTarget:
    """Implements `CoverTarget` with the media use cases.

    The cover's id is its attachment's id. Its content hash covers the stored
    asset's checksum only while the attachment is still the item's cover, so an
    image the person swapped in (or a demoted pack image) reads as an edit.
    """

    def __init__(
        self,
        stores: CoverStores,
        *,
        renderer: CoverRenderer,
        storage: MediaStoragePort,
        policy: AttachmentPolicyPort,
        image_processor: ImageProcessorPort,
    ) -> None:
        self._stores = stores
        self._renderer = renderer
        self._storage = storage
        self._policy = policy
        self._image_processor = image_processor

    async def create(self, item_id: uuid.UUID, name: str, style: str) -> Created:
        """Draw the cover, attach it to the item and set it as the item's cover."""
        png = self._renderer.render(name, style)
        attachment = await UploadAndAttachMedia(
            self._stores.uow(), self._storage, self._policy, self._image_processor
        ).handle(
            UploadAndAttachMediaCommand(
                filename=_cover_filename(name, style),
                content_type="image/png",
                sniffed_content_type="image/png",
                stream=_single_chunk(png),
                target_type=AttachmentTarget.NODE,
                target_id=item_id,
            ),
            SYSTEM_ACTOR,
        )
        try:
            await SetMediaCover(self._stores.uow()).handle(
                SetMediaCoverCommand(
                    asset_id=attachment.asset_id,
                    target_type=AttachmentTarget.NODE,
                    target_id=item_id,
                ),
                SYSTEM_ACTOR,
            )
        except Exception:
            # Not yet recorded by the install, so it would be orphaned.
            await self.remove(attachment.id)
            raise
        return Created(
            entity_id=attachment.id,
            content=_cover_content(name, style, hashlib.sha256(png).hexdigest()),
        )

    async def has_cover(self, item_id: uuid.UUID) -> bool:
        """Whether any image is flagged as the item's cover."""
        async with self._stores.read() as repos:
            attached = await repos.attachments.list_for_target(
                AttachmentTarget.NODE, item_id
            )
        return any(a.attribute_key is AttachmentKey.COVER for a in attached)

    async def inspect(self, cover_id: uuid.UUID) -> Inspection | None:
        """Return the cover as it is now, or `None` if it is gone."""
        async with self._stores.read() as repos:
            attachment = await repos.attachments.get(cover_id)
            if attachment is None:
                return None
            asset = await repos.assets.get(attachment.asset_id)
        if asset is None:
            return None
        parsed = _COVER_FILENAME.fullmatch(asset.filename)
        is_cover = attachment.attribute_key is AttachmentKey.COVER
        return Inspection(
            content=_cover_content(
                parsed["name"] if parsed else None,
                parsed["style"] if parsed else None,
                asset.sha256 if is_cover else None,
            )
        )

    async def remove(self, cover_id: uuid.UUID) -> RemoveResult:
        """Detach the cover, then delete its asset, file and thumbnail."""
        async with self._stores.read() as repos:
            attachment = await repos.attachments.get(cover_id)
        if attachment is None:
            return RemoveResult.ALREADY_GONE
        await DetachMedia(self._stores.uow(), self._storage).handle(
            DetachMediaCommand(
                asset_id=attachment.asset_id,
                target_type=attachment.target_type,
                target_id=attachment.target_id,
                attribute_key=attachment.attribute_key,
            ),
            SYSTEM_ACTOR,
        )
        async with self._stores.read() as repos:
            asset = await repos.assets.get(attachment.asset_id)
        # Detaching orphans the asset only when nothing else uses it.
        if asset is not None and asset.status is MediaStatus.ORPHANED:
            await DeleteMedia(self._stores.uow(), self._storage).handle(
                DeleteMediaCommand(asset_id=asset.id), SYSTEM_ACTOR
            )
        return RemoveResult.REMOVED


# ---- FastAPI providers ----


def get_preset_pack_target(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> PresetPackTarget:
    """Return the preset target over Postgres."""
    return PresetPackTarget(build_preset_stores(session_factory))


def get_graph_pack_target(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> GraphPackTarget:
    """Return the graph target over Postgres."""
    return GraphPackTarget(build_graph_stores(session_factory))


def get_collection_pack_target(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> CollectionPackTarget:
    """Return the collection target over Postgres."""
    return CollectionPackTarget(build_collection_stores(session_factory))


def get_cover_pack_target(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    policy: Annotated[AttachmentPolicyPort, Depends(get_attachment_policy)],
    image_processor: Annotated[ImageProcessorPort, Depends(get_image_processor)],
) -> CoverPackTarget:
    """Return the cover target over Postgres and the configured media storage."""
    return CoverPackTarget(
        build_cover_stores(session_factory),
        renderer=PillowCoverRenderer(),
        storage=storage,
        policy=policy,
        image_processor=image_processor,
    )
