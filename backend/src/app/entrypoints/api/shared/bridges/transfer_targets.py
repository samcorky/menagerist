"""Adapters that let the transfer module drive the graph, presets and collections."""

import copy
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, cast

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.choice_list_source import PresetChoiceListSource
from app.entrypoints.api.shared.bridges.collection_conditions import (
    build_search_graph_repos,
)
from app.entrypoints.api.shared.bridges.collection_definitions import (
    GraphDefinitionChecker,
)
from app.entrypoints.api.shared.bridges.collection_items import GraphItemLookup
from app.entrypoints.api.shared.bridges.preset_usage import GraphPresetUsage
from app.entrypoints.api.shared.bridges.transfer_fields import (
    attribute_problems,
    field_specs,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
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
from app.modules.collections.application.get_collection import (
    GetCollection,
    GetCollectionQuery,
)
from app.modules.collections.application.purge_collection import (
    PurgeCollection,
    PurgeCollectionCommand,
)
from app.modules.collections.application.purge_item_memberships import (
    PurgeItemMemberships,
    PurgeItemMembershipsCommand,
)
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.definition_checker import DefinitionChecker
from app.modules.collections.ports.item_lookup import ItemLookup
from app.modules.collections.ports.unit_of_work import (
    CollectionsRepos,
    CollectionsUnitOfWork,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_graph_repos,
    create_graph_uow,
    create_in_memory_graph_uow,
)
from app.modules.graph.application.choice_lists import (
    LIST_KEY,
    NAMESPACE,
    resolve_choice_lists,
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
from app.modules.graph.application.delete_edge_type import (
    DeleteEdgeType,
    DeleteEdgeTypeCommand,
)
from app.modules.graph.application.delete_unused_node_type import (
    DeleteUnusedNodeType,
    DeleteUnusedNodeTypeCommand,
)
from app.modules.graph.application.get_edge_type import GetEdgeType, GetEdgeTypeQuery
from app.modules.graph.application.get_node import GetNode, GetNodeQuery
from app.modules.graph.application.get_node_type import GetNodeType, GetNodeTypeQuery
from app.modules.graph.application.list_edges import ListEdges, ListEdgesQuery
from app.modules.graph.application.purge_edge import PurgeEdge, PurgeEdgeCommand
from app.modules.graph.application.purge_node import PurgeNode, PurgeNodeCommand
from app.modules.graph.domain.edge import Edge  # noqa: TC001
from app.modules.graph.domain.edge_type import EdgeType  # noqa: TC001
from app.modules.graph.domain.errors import (
    EdgeTypeInUseError,
    EdgeTypeNotFoundError,
    NodeTypeInUseError,
    NodeTypeNotFoundError,
)
from app.modules.graph.domain.node import Node  # noqa: TC001
from app.modules.graph.domain.node_type import NodeType  # noqa: TC001
from app.modules.graph.ports.choice_list_source import ChoiceListSource
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.modules.media.adapters.persistence.unit_of_work import build_media_repos
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.modules.media.ports.unit_of_work import MediaRepos
from app.modules.presets.adapters.persistence.unit_of_work import (
    build_preset_repos,
    create_in_memory_preset_uow,
    create_preset_uow,
)
from app.modules.presets.application.delete_preset import (
    DeletePreset,
    DeletePresetCommand,
)
from app.modules.presets.application.export_presets import (
    ExportPresets,
    ExportPresetsQuery,
)
from app.modules.presets.application.import_presets import (
    ImportPresets,
    ImportPresetsCommand,
)
from app.modules.presets.application.match_presets import (
    MatchPresets,
    MatchPresetsQuery,
)
from app.modules.presets.application.pack import check_presets
from app.modules.presets.domain.errors import PresetInUseError, PresetNotFoundError
from app.modules.presets.domain.preset import Preset  # noqa: TC001
from app.modules.presets.ports.preset_usage import PresetUsage
from app.modules.presets.ports.unit_of_work import PresetRepos, PresetUnitOfWork
from app.modules.transfer.domain.bundle import (
    PRESET_MARKER,
    BundleCollection,
    BundleConnection,
    BundleItem,
    BundleItemType,
    BundlePreset,
    BundleRelationshipType,
    resolve_preset_refs,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.ports.targets import (
    Created,
    Inspection,
    PresetOutcome,
    RemoveResult,
)
from app.platform.database import get_session_factory
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.domain.edge_type import Holder
    from app.modules.transfer.domain.tabular import FieldSpec
    from app.shared_kernel.access_guard import AccessGuard

_PAGE = 1
_EDGE_PAGE = 200
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
    usage: Callable[[ContentFilter], AbstractAsyncContextManager[PresetUsage]]


@dataclass(kw_only=True)
class GraphStores:
    """Factories the graph target uses; each call opens fresh storage access."""

    uow: Callable[[], GraphUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[GraphRepos]]
    media: Callable[[], AbstractAsyncContextManager[MediaRepos]]
    choice_lists: Callable[
        [ContentFilter], AbstractAsyncContextManager[ChoiceListSource]
    ]
    collections: Callable[[], AbstractAsyncContextManager[CollectionsRepos]]
    collections_uow: Callable[[], CollectionsUnitOfWork]


@dataclass(kw_only=True)
class CollectionStores:
    """Factories the collection target uses; each call opens fresh storage access."""

    uow: Callable[[], CollectionsUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[CollectionsRepos]]
    items: Callable[[], AbstractAsyncContextManager[ItemLookup]]
    checker: Callable[[], AbstractAsyncContextManager[DefinitionChecker]]


def build_in_memory_collections_repos() -> CollectionsRepos:
    """Return empty in-memory collections repositories, for tests."""
    collections = InMemoryCollectionRepository()
    return CollectionsRepos(
        collections=collections,
        memberships=InMemoryMembershipRepository(collections),
    )


def in_memory_preset_stores(
    preset_repos: PresetRepos, graph_repos: GraphRepos
) -> PresetStores:
    """Stores over in-memory repositories, for tests."""

    @asynccontextmanager
    async def read() -> AsyncIterator[PresetRepos]:
        yield preset_repos

    @asynccontextmanager
    async def usage(scope: ContentFilter) -> AsyncIterator[PresetUsage]:
        yield GraphPresetUsage(graph_repos, scope=scope)

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
    async def choice_lists(scope: ContentFilter) -> AsyncIterator[ChoiceListSource]:
        yield PresetChoiceListSource(preset_repos, scope)

    @asynccontextmanager
    async def collections() -> AsyncIterator[CollectionsRepos]:
        yield collection_repos

    return GraphStores(
        uow=lambda: create_in_memory_graph_uow(graph_repos),
        read=read,
        media=media,
        choice_lists=choice_lists,
        collections=collections,
        collections_uow=lambda: create_in_memory_collections_uow(collection_repos),
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

    @asynccontextmanager
    async def checker() -> AsyncIterator[DefinitionChecker]:
        yield GraphDefinitionChecker(graph_repos)

    return CollectionStores(
        uow=lambda: create_in_memory_collections_uow(collection_repos),
        read=read,
        items=items,
        checker=checker,
    )


def build_preset_stores(
    session_factory: async_sessionmaker[AsyncSession],
) -> PresetStores:
    """Stores over Postgres sessions."""

    @asynccontextmanager
    async def read() -> AsyncIterator[PresetRepos]:
        async with session_factory() as session:
            yield build_preset_repos(session)

    @asynccontextmanager
    async def usage(scope: ContentFilter) -> AsyncIterator[PresetUsage]:
        async with session_factory() as session:
            yield GraphPresetUsage(build_graph_repos(session), scope=scope)

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
    async def choice_lists(scope: ContentFilter) -> AsyncIterator[ChoiceListSource]:
        async with session_factory() as session:
            yield PresetChoiceListSource(build_preset_repos(session), scope)

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
        collections_uow=lambda: create_collections_uow(session_factory),
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

    @asynccontextmanager
    async def checker() -> AsyncIterator[DefinitionChecker]:
        # The same checker, over the same repositories, as `POST /collection`.
        async with session_factory() as session:
            yield GraphDefinitionChecker(build_search_graph_repos(session))

    return CollectionStores(
        uow=lambda: create_collections_uow(session_factory),
        read=read,
        items=items,
        checker=checker,
    )


# ---- content: what the pack defines, read back from what was stored ----


def _preset_content(p: Preset) -> dict[str, Any]:
    return {
        "kind": p.kind,
        "label": p.label,
        "description": p.description,
        "definition": copy.deepcopy(p.definition),
    }


def _node_type_content(t: NodeType) -> dict[str, Any]:
    content: dict[str, Any] = {
        "slug": str(t.slug),
        "label": t.label,
        "description": t.description,
        "attributes_schema": copy.deepcopy(t.attributes_schema),
    }
    # Only when set, so types installed before packs had icons keep their hash.
    if t.icon is not None:
        content["icon"] = t.icon
    if t.colour is not None:
        content["colour"] = t.colour
    if t.parent is not None:
        content["parent"] = t.parent
    return content


def _item_type_spec(
    node_type: NodeType, parents: Mapping[str, NodeType]
) -> BundleItemType:
    """The bundle form of an item type, its `ref` its id and its parent's id."""
    parent = parents.get(node_type.parent) if node_type.parent else None
    return BundleItemType(
        ref=str(node_type.id),
        slug=str(node_type.slug),
        label=node_type.label,
        description=node_type.description,
        attributes_schema=_marked(node_type.attributes_schema),
        icon=node_type.icon,
        colour=node_type.colour,
        parent=str(parent.id) if parent is not None else None,
    )


def _edge_type_content(t: EdgeType) -> dict[str, Any]:
    content: dict[str, Any] = {
        "slug": str(t.slug),
        "label": t.label,
        "reverse_label": t.reverse_label,
        "description": t.description,
        "directional": t.directional,
        "attributes_schema": copy.deepcopy(t.attributes_schema),
    }
    # Only when set, so types installed before `holder` existed hash as they did.
    if t.holder != "none":
        content["holder"] = t.holder
    # Likewise for the item type limits.
    if t.source_types:
        content["source_types"] = list(t.source_types)
    if t.target_types:
        content["target_types"] = list(t.target_types)
    return content


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
    name: str,
    description: str | None,
    members: Sequence[uuid.UUID],
    definition: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "name": name,
        "description": description,
        "members": sorted(str(m) for m in members),
    }
    if definition is not None:
        content["definition"] = dict(definition)
    return content


# A cover's file is named "<item name> (<style>).png", which is how `inspect`
# recovers name and style: the media module stores nothing else about it.


def _marked(schema: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of `schema` with each linked list named by a `$preset` marker."""
    if schema is None:
        return None
    result = copy.deepcopy(schema)
    for prop in result.get("properties", {}).values():
        extension = prop.get(NAMESPACE) if isinstance(prop, dict) else None
        if isinstance(extension, dict) and LIST_KEY in extension:
            extension[LIST_KEY] = {PRESET_MARKER: str(extension[LIST_KEY])}
    return result


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


def _preset_items(presets: Sequence[BundlePreset]) -> list[dict[str, Any]]:
    return [
        {
            "kind": p.kind,
            "label": p.label,
            "description": p.description,
            "definition": copy.deepcopy(p.definition),
        }
        for p in presets
    ]


class PresetPackTarget:
    """Implements `PresetTarget` with the presets use cases.

    Presets belong to a person, so every call runs as `actor` and sees only their own.
    """

    def __init__(
        self, stores: PresetStores, actor: Actor, *, access: AccessGuard | None = None
    ) -> None:
        self._stores = stores
        self._actor = actor
        self._access = access or get_access_guard()
        self._scope = self._access.scope_for(actor)

    async def ensure(self, presets: Sequence[BundlePreset]) -> list[PresetOutcome]:
        """Create each preset unless an identical one exists."""
        if not presets:
            return []
        command = ImportPresetsCommand(items=_preset_items(presets))
        result = await ImportPresets(self._stores.uow(), self._access).handle(
            command, self._actor
        )
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

    async def existing(self, presets: Sequence[BundlePreset]) -> list[bool]:
        """Say, in order, whether the person already has an identical preset."""
        items = [
            {"kind": p.kind, "label": p.label, "definition": p.definition}
            for p in presets
        ]
        async with self._stores.read() as repos:
            return await MatchPresets(repos, self._access).handle(
                MatchPresetsQuery(items=items), self._actor
            )

    async def check(self, presets: Sequence[BundlePreset]) -> None:
        """Refuse the presets as `ImportPresets` would; nothing is stored."""
        check_presets(_preset_items(presets))

    async def read(self, preset_ids: Sequence[uuid.UUID]) -> list[BundlePreset]:
        """Return the person's presets with `preset_ids`, each `ref` its id."""
        async with self._stores.read() as repos:
            found = await ExportPresets(repos, self._access).handle(
                ExportPresetsQuery(ids=list(preset_ids)), self._actor
            )
        return [
            BundlePreset(
                ref=str(p.id),
                kind=p.kind,
                label=p.label,
                description=p.description,
                definition=copy.deepcopy(p.definition),
            )
            for p in found
        ]

    async def inspect(self, preset_id: uuid.UUID) -> Inspection | None:
        """Return the preset as it is now, or `None` if it is gone."""
        async with self._stores.read() as repos:
            preset = await repos.presets.get(preset_id, scope=self._scope)
        return None if preset is None else Inspection(content=_preset_content(preset))

    async def remove(self, preset_id: uuid.UUID) -> RemoveResult:
        """Remove the preset unless an item type still uses it."""
        async with self._stores.usage(self._scope) as usage:
            try:
                await DeletePreset(self._stores.uow(), self._access, usage).handle(
                    DeletePresetCommand(preset_id=preset_id), self._actor
                )
            except PresetInUseError:
                return RemoveResult.REFUSED_IN_USE
            except PresetNotFoundError:
                return RemoveResult.ALREADY_GONE
        return RemoveResult.REMOVED


class GraphPackTarget:
    """Implements `GraphTarget` with the graph use cases, run as `actor`.

    Items, connections and types are the actor's own. A type is removed as the system
    actor, by id from the actor's own installation, after the in-use check.
    """

    def __init__(
        self, stores: GraphStores, actor: Actor, *, access: AccessGuard | None = None
    ) -> None:
        self._stores = stores
        self._actor = actor
        self._access = access or get_access_guard()
        self._scope = self._access.scope_for(actor)

    async def slug_taken(self, kind: EntityKind, slug: str) -> bool:
        """Whether a live type of `kind` already has `slug`."""
        async with self._stores.read() as repos:
            # Pack slugs are already normalised; edge types normalise on create.
            if kind is EntityKind.ITEM_TYPE:
                return (
                    await repos.node_types.get_by_slug(slug, scope=self._scope)
                    is not None
                )
            return (
                await repos.edge_types.get_by_slug(slugify(slug), scope=self._scope)
                is not None
            )

    async def find_items_by_field(
        self,
        type_slug: str,
        key: str,
        value: str | int | float,
        *,
        limit: int = 2,
        ignore_case: bool = False,
    ) -> list[uuid.UUID]:
        """Return ids of the actor's items of `type_slug` whose `key` equals `value`."""
        async with self._stores.read() as repos:
            if key == "name":
                return await repos.nodes.ids_with_name(
                    type_slug,
                    str(value),
                    scope=self._scope,
                    limit=limit,
                    ignore_case=ignore_case,
                )
            return await repos.nodes.ids_with_attribute_value(
                type_slug, key, value, scope=self._scope, limit=limit
            )

    async def create_relationship_type(
        self, spec: BundleRelationshipType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the relationship type."""
        command = CreateEdgeTypeCommand(
            slug=spec.slug,
            label=spec.label,
            reverse_label=spec.reverse_label,
            description=spec.description,
            directional=spec.directional,
            attributes_schema=_resolved(spec.attributes_schema, presets),
            holder=cast("Holder", spec.holder),
            source_types=spec.source_types,
            target_types=spec.target_types,
        )
        async with self._stores.choice_lists(self._scope) as source:
            edge_type = await CreateEdgeType(
                self._stores.uow(), self._access, source
            ).handle(command, self._actor)
        return Created(entity_id=edge_type.id, content=_edge_type_content(edge_type))

    async def create_item_type(
        self,
        spec: BundleItemType,
        presets: Mapping[str, uuid.UUID],
        *,
        parent_slug: str | None = None,
    ) -> Created:
        """Create the item type, under `parent_slug` when it is a subtype."""
        command = CreateNodeTypeCommand(
            slug=spec.slug,
            label=spec.label,
            description=spec.description,
            attributes_schema=_resolved(spec.attributes_schema, presets),
            icon=spec.icon,
            colour=spec.colour,
            parent=parent_slug,
        )
        async with self._stores.choice_lists(self._scope) as source:
            node_type = await CreateNodeType(
                self._stores.uow(), self._access, source
            ).handle(command, self._actor)
        return Created(entity_id=node_type.id, content=_node_type_content(node_type))

    async def read_item_types(
        self, type_ids: Sequence[uuid.UUID]
    ) -> list[BundleItemType]:
        """Return the person's item types with `type_ids`, each `ref` its id.

        A subtype's parent is included after the types asked for, and named by id.
        """
        found: list[BundleItemType] = []
        async with self._stores.read() as repos:
            asked = [
                await GetNodeType(repos, self._access).handle(
                    GetNodeTypeQuery(node_type_id=type_id), self._actor
                )
                for type_id in type_ids
            ]
            parents: dict[str, NodeType] = {}
            for node_type in asked:
                if node_type.parent is None or node_type.parent in parents:
                    continue
                parent = await repos.node_types.get_by_slug(
                    node_type.parent, scope=self._scope
                )
                if parent is not None:
                    parents[node_type.parent] = parent
            seen = {t.id for t in asked}
            extra = [p for p in parents.values() if p.id not in seen]
            found = [_item_type_spec(t, parents) for t in [*asked, *extra]]
        return found

    async def read_relationship_types(
        self, type_ids: Sequence[uuid.UUID]
    ) -> list[BundleRelationshipType]:
        """Return the person's relationship types with `type_ids`, each `ref` its id."""
        found: list[BundleRelationshipType] = []
        async with self._stores.read() as repos:
            for type_id in type_ids:
                edge_type = await GetEdgeType(repos, self._access).handle(
                    GetEdgeTypeQuery(edge_type_id=type_id), self._actor
                )
                found.append(
                    BundleRelationshipType(
                        ref=str(edge_type.id),
                        slug=str(edge_type.slug),
                        label=edge_type.label,
                        reverse_label=edge_type.reverse_label,
                        description=edge_type.description,
                        directional=edge_type.directional,
                        attributes_schema=_marked(edge_type.attributes_schema),
                        holder=edge_type.holder,
                        source_types=edge_type.source_types,
                        target_types=edge_type.target_types,
                    )
                )
        return found

    async def item_type_field_keys(self, slug: str) -> frozenset[str] | None:
        """Return the field keys of the person's item type `slug`, or `None`."""
        async with self._stores.read() as repos:
            node_type = await repos.node_types.get_by_slug(slug, scope=self._scope)
        if node_type is None:
            return None
        properties = (node_type.attributes_schema or {}).get("properties", {})
        return frozenset(properties)

    async def _resolved_schema(self, slug: str) -> dict[str, Any] | None:
        """The person's item type `slug` as a schema with its choice lists filled in."""
        async with self._stores.read() as repos:
            node_type = await repos.node_types.get_by_slug(slug, scope=self._scope)
        if node_type is None:
            return None
        schema = node_type.attributes_schema or {"type": "object", "properties": {}}
        async with self._stores.choice_lists(self._scope) as source:
            return await resolve_choice_lists(schema, source)

    async def item_type_fields(self, slug: str) -> list[FieldSpec] | None:
        """Describe the fields of the person's item type `slug`, or `None`."""
        schema = await self._resolved_schema(slug)
        return None if schema is None else field_specs(schema)

    async def check_item_attributes(
        self, slug: str, attributes: Mapping[str, Any]
    ) -> list[str]:
        """Return a message for each value that breaks the type's schema."""
        schema = await self._resolved_schema(slug)
        return [] if schema is None else attribute_problems(schema, attributes)

    async def read_items(self, item_ids: Sequence[uuid.UUID]) -> list[BundleItem]:
        """Return the person's items with `item_ids`, each `ref` its id."""
        found: list[BundleItem] = []
        async with self._stores.read() as repos:
            type_ids: dict[str, str | None] = {}
            for item_id in item_ids:
                node = await GetNode(repos, self._access).handle(
                    GetNodeQuery(node_id=item_id), self._actor
                )
                slug = node.type or ""
                if slug not in type_ids:
                    node_type = await repos.node_types.get_by_slug(
                        slug, scope=self._scope
                    )
                    type_ids[slug] = None if node_type is None else str(node_type.id)
                found.append(
                    BundleItem(
                        ref=str(node.id),
                        type_ref=type_ids[slug],
                        name=node.name,
                        description=node.description,
                        attributes=node.attributes,
                        tags=tuple(node.tags),
                        extra_schema=node.extra_schema,
                    )
                )
        return found

    async def read_connections(
        self, item_ids: Sequence[uuid.UUID]
    ) -> list[BundleConnection]:
        """Return the connections that join two of `item_ids`."""
        async with self._stores.read() as repos:
            edges = await self._edges_between(repos, item_ids)
            type_ids: dict[str, str | None] = {}
            found: list[BundleConnection] = []
            for edge in edges:
                if edge.type not in type_ids:
                    edge_type = await repos.edge_types.get_by_slug(
                        edge.type, scope=self._scope
                    )
                    type_ids[edge.type] = (
                        None if edge_type is None else str(edge_type.id)
                    )
                type_ref = type_ids[edge.type]
                if type_ref is not None:
                    found.append(
                        BundleConnection(
                            source_ref=str(edge.source_id),
                            target_ref=str(edge.target_id),
                            type_ref=type_ref,
                            attributes=edge.attributes,
                        )
                    )
        return found

    async def _edges_between(
        self, repos: GraphRepos, item_ids: Sequence[uuid.UUID]
    ) -> list[Edge]:
        """Each live connection with both ends among `item_ids`, once."""
        wanted = set(item_ids)
        edges: dict[uuid.UUID, Edge] = {}
        for item_id in item_ids:
            after: uuid.UUID | None = None
            while True:
                page = await ListEdges(repos, self._access).handle(
                    ListEdgesQuery(node_id=item_id, after=after, limit=_EDGE_PAGE),
                    self._actor,
                )
                for edge in page:
                    if edge.source_id in wanted and edge.target_id in wanted:
                        edges.setdefault(edge.id, edge)
                if len(page) < _EDGE_PAGE:
                    break
                after = page[-1].id
        return list(edges.values())

    async def create_item(self, spec: BundleItem, *, type_slug: str | None) -> Created:
        """Create the item under `type_slug`."""
        command = CreateNodeCommand(
            name=spec.name,
            type=type_slug,
            description=spec.description,
            attributes=spec.attributes,
            tags=list(spec.tags),
            extra_schema=spec.extra_schema,
        )
        async with self._stores.choice_lists(self._scope) as source:
            node = await CreateNode(self._stores.uow(), self._access, source).handle(
                command, self._actor
            )
        return Created(entity_id=node.id, content=_node_content(node))

    async def create_connection(
        self,
        spec: BundleConnection,
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
        async with self._stores.choice_lists(self._scope) as source:
            edge = await CreateEdge(self._stores.uow(), self._access, source).handle(
                command, self._actor
            )
        return Created(entity_id=edge.id, content=_edge_content(edge))

    async def connection_exists(
        self, source_id: uuid.UUID, target_id: uuid.UUID, type_slug: str
    ) -> bool:
        """Whether a live connection of `type_slug` already runs source to target."""
        async with self._stores.read() as repos:
            after: uuid.UUID | None = None
            while True:
                page = await repos.edges.list_for_node(
                    source_id, scope=self._scope, after=after, limit=_EDGE_PAGE
                )
                if any(
                    e.source_id == source_id
                    and e.target_id == target_id
                    and e.type == type_slug
                    for e in page
                ):
                    return True
                if len(page) < _EDGE_PAGE:
                    return False
                after = page[-1].id

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
                edge = await repos.edges.get(entity_id, scope=self._scope)
                return None if edge is None else Inspection(content=_edge_content(edge))
        raise ValueError(f"The graph target does not handle {kind.value} entities")

    async def _inspect_item(
        self, repos: GraphRepos, entity_id: uuid.UUID
    ) -> Inspection | None:
        node = await repos.nodes.get(entity_id, scope=self._scope)
        if node is None:
            return None
        touched = await repos.edges.list_for_node(
            node.id, scope=self._scope, after=None, limit=_PAGE
        )
        async with self._stores.media() as media:
            files = await media.attachments.list_for_target(
                AttachmentTarget.NODE, node.id, scope=self._scope
            )
        in_collection = await self._on_live_collection(node.id)
        return Inspection(
            content=_node_content(node),
            has_user_data=bool(touched or files or in_collection),
        )

    async def _on_live_collection(self, item_id: uuid.UUID) -> bool:
        """Whether any live collection holds the item."""
        async with self._stores.collections() as repos:
            for collection_id in await repos.memberships.collection_ids_for(
                item_id, scope=self._scope
            ):
                if await repos.collections.get(collection_id, scope=self._scope):
                    return True
        return False

    async def _inspect_item_type(
        self, repos: GraphRepos, entity_id: uuid.UUID
    ) -> Inspection | None:
        node_type = await repos.node_types.get(entity_id, scope=self._scope)
        if node_type is None:
            return None
        items = await repos.nodes.list(
            scope=self._scope,
            after=None,
            limit=_PAGE,
            type=str(node_type.slug),
        )
        return Inspection(
            content=_node_type_content(node_type), still_in_use=bool(items)
        )

    async def _inspect_relationship_type(
        self, repos: GraphRepos, entity_id: uuid.UUID
    ) -> Inspection | None:
        edge_type = await repos.edge_types.get(entity_id, scope=self._scope)
        if edge_type is None:
            return None
        in_use = await repos.edges.has_edges_of_type(
            str(edge_type.slug), scope=self._scope
        )
        return Inspection(content=_edge_type_content(edge_type), still_in_use=in_use)

    async def remove(self, kind: EntityKind, entity_id: uuid.UUID) -> RemoveResult:
        """Remove the entity: items and connections hard, types soft.

        Types stay soft-deleted so their slugs stay reusable and other rows may
        still name them.
        """
        if kind not in _GRAPH_KINDS:
            raise ValueError(f"The graph target does not handle {kind.value} entities")
        if kind is EntityKind.ITEM:
            return await self._purge_item(entity_id)
        if kind is EntityKind.CONNECTION:
            return await self._purge_connection(entity_id)
        uow = self._stores.uow()
        try:
            if kind is EntityKind.ITEM_TYPE:
                # Check and delete in one locked transaction: an item added
                # meanwhile keeps the type instead of losing it.
                await DeleteUnusedNodeType(uow, self._access).handle(
                    DeleteUnusedNodeTypeCommand(node_type_id=entity_id), SYSTEM_ACTOR
                )
            else:
                await DeleteEdgeType(uow, self._access).handle(
                    DeleteEdgeTypeCommand(edge_type_id=entity_id), SYSTEM_ACTOR
                )
        except NodeTypeNotFoundError, EdgeTypeNotFoundError:
            return RemoveResult.ALREADY_GONE
        except EdgeTypeInUseError, NodeTypeInUseError:
            return RemoveResult.REFUSED_IN_USE
        return RemoveResult.REMOVED

    async def _purge_item(self, item_id: uuid.UUID) -> RemoveResult:
        """Hard-delete an item the actor owns, with its connections and memberships.

        The item goes last, so a run interrupted before that finds it and repeats.
        """
        async with self._stores.read() as repos:
            if await repos.nodes.get(item_id, scope=self._scope) is None:
                return RemoveResult.ALREADY_GONE
        await PurgeItemMemberships(self._stores.collections_uow(), self._access).handle(
            PurgeItemMembershipsCommand(item_id=item_id), SYSTEM_ACTOR
        )
        await PurgeNode(self._stores.uow(), self._access).handle(
            PurgeNodeCommand(node_id=item_id), SYSTEM_ACTOR
        )
        return RemoveResult.REMOVED

    async def _purge_connection(self, edge_id: uuid.UUID) -> RemoveResult:
        """Hard-delete a connection the actor owns."""
        async with self._stores.read() as repos:
            if await repos.edges.get(edge_id, scope=self._scope) is None:
                return RemoveResult.ALREADY_GONE
        await PurgeEdge(self._stores.uow(), self._access).handle(
            PurgeEdgeCommand(edge_id=edge_id), SYSTEM_ACTOR
        )
        return RemoveResult.REMOVED


class CollectionPackTarget:
    """Implements `CollectionTarget` with the collections use cases, run as `actor`."""

    def __init__(
        self,
        stores: CollectionStores,
        actor: Actor,
        *,
        access: AccessGuard | None = None,
    ) -> None:
        self._stores = stores
        self._actor = actor
        self._access = access or get_access_guard()
        self._scope = self._access.scope_for(actor)

    async def create_collection(
        self, spec: BundleCollection, *, item_ids: Sequence[uuid.UUID]
    ) -> Created:
        """Create the collection, put the items on it and return what was stored."""
        async with self._stores.checker() as checker:
            collection = await CreateCollection(
                self._stores.uow(), self._access, checker
            ).handle(
                CreateCollectionCommand(
                    name=spec.name,
                    description=spec.description,
                    definition=(
                        None if spec.definition is None else dict(spec.definition)
                    ),
                ),
                self._actor,
            )
        try:
            if spec.definition is None:
                async with self._stores.items() as items:
                    await AddItemsToCollection(
                        self._stores.uow(), self._access, items
                    ).handle(
                        AddItemsToCollectionCommand(
                            collection_id=collection.id, item_ids=list(item_ids)
                        ),
                        self._actor,
                    )
            inspection = await self.inspect(collection.id)
        except Exception:
            # Not yet recorded by the install, so it would be orphaned.
            await self.remove(collection.id)
            raise
        if inspection is None:  # pragma: no cover - only if deleted concurrently
            raise RuntimeError(f"Collection {collection.id} vanished after creation")
        return Created(entity_id=collection.id, content=inspection.content)

    async def read_collections(
        self, collection_ids: Sequence[uuid.UUID]
    ) -> list[BundleCollection]:
        """Return the person's collections with `collection_ids`, each `ref` its id."""
        found: list[BundleCollection] = []
        for collection_id in collection_ids:
            async with (
                self._stores.read() as repos,
                self._stores.items() as items,
                self._stores.checker() as checker,
            ):
                # Raises if it is not the person's own, as for every other kind.
                await GetCollection(repos, self._access, items, checker).handle(
                    GetCollectionQuery(collection_id=collection_id), self._actor
                )
                collection = await repos.collections.get(
                    collection_id, scope=self._scope
                )
                if collection is None:  # pragma: no cover - guarded just above
                    raise CollectionNotFoundError(f"Collection {collection_id} gone")
                stored = await repos.memberships.item_ids(
                    collection_id, scope=self._scope
                )
                live = await items.live_ids(list(stored), self._scope)
            is_smart = collection.definition is not None
            found.append(
                BundleCollection(
                    ref=str(collection.id),
                    name=collection.name,
                    description=collection.description,
                    item_refs=(() if is_smart else tuple(sorted(str(i) for i in live))),
                    definition=(
                        copy.deepcopy(dict(collection.definition))
                        if collection.definition is not None
                        else None
                    ),
                )
            )
        return found

    async def inspect(self, collection_id: uuid.UUID) -> Inspection | None:
        """Return the collection as it is now, or `None` if it is gone.

        Members are the stored memberships whose items are still live, as the
        collection page shows them, so a deleted item reads as a membership change.
        """
        async with self._stores.read() as repos, self._stores.items() as items:
            collection = await repos.collections.get(collection_id, scope=self._scope)
            if collection is None:
                return None
            stored = await repos.memberships.item_ids(collection_id, scope=self._scope)
            live = await items.live_ids(list(stored), self._scope)
        return Inspection(
            content=_collection_content(
                collection.name,
                collection.description,
                list(live),
                collection.definition,
            )
        )

    async def remove(self, collection_id: uuid.UUID) -> RemoveResult:
        """Hard-delete a collection the actor owns, with its memberships."""
        async with self._stores.read() as repos:
            if await repos.collections.get(collection_id, scope=self._scope) is None:
                return RemoveResult.ALREADY_GONE
        await PurgeCollection(self._stores.uow(), self._access).handle(
            PurgeCollectionCommand(collection_id=collection_id), SYSTEM_ACTOR
        )
        return RemoveResult.REMOVED


# ---- FastAPI providers ----


def get_preset_pack_target(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> PresetPackTarget:
    """Return the preset target over Postgres, acting as the signed-in person."""
    return PresetPackTarget(build_preset_stores(session_factory), actor)


def get_graph_pack_target(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> GraphPackTarget:
    """Return the graph target over Postgres, acting as the signed-in person."""
    return GraphPackTarget(build_graph_stores(session_factory), actor)


def get_collection_pack_target(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> CollectionPackTarget:
    """Return the collection target over Postgres, acting as the signed-in person."""
    return CollectionPackTarget(build_collection_stores(session_factory), actor)
