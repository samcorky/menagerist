"""The search module's view of the modules that own what it finds.

Each source asks the owner's own use case, so the owner keeps its permission
checks, content filtering and accent folding. A source the actor may not use
raises `ForbiddenError` from that use case, which the search treats as "leave
this kind out".
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.modules.collections.adapters.api.dependencies import (
    get_list_collections_use_case,
    get_resolve_collection_use_case,
)
from app.modules.collections.application.list_collections import (
    ListCollections,
    ListCollectionsQuery,
)
from app.modules.collections.application.resolve_collection import (
    ResolveCollection,
    ResolveCollectionQuery,
)
from app.modules.examples.adapters.api.dependencies import (
    get_list_example_packs_use_case,
)
from app.modules.examples.application.list_example_packs import (
    ListExamplePacks,
    ListExamplePacksQuery,
)
from app.modules.graph.adapters.api.dependencies import (
    get_list_node_types_use_case,
    get_list_nodes_use_case,
)
from app.modules.graph.application.list_node_types import (
    ListNodeTypes,
    ListNodeTypesQuery,
)
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.identity.adapters.api.dependencies import get_list_users_use_case
from app.modules.identity.application.list_users import ListUsers, ListUsersQuery
from app.modules.presets.adapters.api.dependencies import get_list_presets_use_case
from app.modules.presets.application.list_presets import ListPresets, ListPresetsQuery
from app.modules.scheduling.adapters.api.dependencies import get_list_jobs_use_case
from app.modules.scheduling.application.list_jobs import ListJobs, ListJobsQuery
from app.modules.search.domain.search_hit import SearchHit, SearchKind
from app.modules.settings.adapters.api.dependencies import (
    get_list_my_settings_use_case,
    get_list_settings_use_case,
)
from app.modules.settings.application.list_my_settings import (
    ListMySettings,
    ListMySettingsQuery,
)
from app.modules.settings.application.list_settings import (
    ListSettings,
    ListSettingsQuery,
)
from app.platform.config import get_server_settings
from app.shared_kernel.paging import MAX_PAGE_ROWS
from app.shared_kernel.text import fold

if TYPE_CHECKING:
    from app.modules.search.ports.search_source import SearchSource
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.paging import Cursor

# Item types and the two registries are small and have no text filter of their own,
# so they are read whole, a page at a time, and filtered here.
_TYPE_PAGE = 100
_TYPE_CAP = 10_000


def _mentions(query: str, *texts: str | None) -> bool:
    needle = fold(query.strip())
    return any(needle in fold(text) for text in texts if text)


class ItemSource:
    """Items, matched by the graph module on name, description and field values.

    Given a collection, the items in it are fetched on their own, so a good match
    there is not crowded out by better-scoring ones elsewhere, then marked.
    """

    kind = SearchKind.ITEM

    def __init__(self, use_case: ListNodes, resolver: ResolveCollection) -> None:
        self._use_case = use_case
        self._resolver = resolver

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return items matching `query`, marking those in `collection`."""
        members: list[Any] = []
        if collection is not None:
            collection_id = await self._resolver.handle(
                ResolveCollectionQuery(id_or_slug=collection), actor
            )
            members = (
                await self._use_case.handle(
                    ListNodesQuery(q=query, limit=limit, collection=collection_id),
                    actor,
                )
            ).items
        everywhere = (
            await self._use_case.handle(ListNodesQuery(q=query, limit=limit), actor)
        ).items
        member_ids = {node.id for node in members}
        nodes = members + [node for node in everywhere if node.id not in member_ids]
        return [
            SearchHit(
                kind=self.kind,
                ref=str(node.id),
                title=node.name,
                description=node.description,
                group=node.type,
                attributes=node.attributes,
                in_collection=node.id in member_ids,
            )
            for node in nodes
        ]


class CollectionSource:
    """Collections, matched by the collections module on name and description."""

    kind = SearchKind.COLLECTION

    def __init__(self, use_case: ListCollections) -> None:
        self._use_case = use_case

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return collections matching `query`."""
        result = await self._use_case.handle(
            ListCollectionsQuery(q=query, limit=limit), actor
        )
        return [
            SearchHit(
                kind=self.kind,
                ref=str(summary.collection.id),
                title=summary.collection.name,
                description=summary.collection.description,
                slug=str(summary.collection.slug),
                item_count=summary.item_count,
            )
            for summary in result.items
        ]


class ItemTypeSource:
    """Item types, read in full from the graph module and matched on label and slug."""

    kind = SearchKind.ITEM_TYPE

    def __init__(self, use_case: ListNodeTypes) -> None:
        self._use_case = use_case

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return item types matching `query`."""
        hits: list[SearchHit] = []
        after: Cursor | None = None
        seen = 0
        while seen < _TYPE_CAP:
            page = await self._use_case.handle(
                ListNodeTypesQuery(after=after, limit=_TYPE_PAGE), actor
            )
            seen += len(page.items)
            hits.extend(
                SearchHit(
                    kind=self.kind,
                    ref=str(node_type.slug),
                    title=node_type.label,
                    description=node_type.description,
                )
                for node_type in page.items
                if _mentions(query, node_type.label, str(node_type.slug))
            )
            if page.next is None:
                break
            after = page.next
        return hits


class SavedFieldSource:
    """Saved fields, field sets and choice lists, matched on name and description.

    The presets are read in full, a page at a time, and filtered here: `ListPresets`
    can only match a label, without folding accents.
    """

    kind = SearchKind.SAVED_FIELD

    def __init__(self, use_case: ListPresets) -> None:
        self._use_case = use_case

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return the actor's saved fields matching `query`."""
        hits: list[SearchHit] = []
        after: Cursor | None = None
        seen = 0
        while seen < _TYPE_CAP:
            page = await self._use_case.handle(
                ListPresetsQuery(after=after, limit=_TYPE_PAGE), actor
            )
            seen += len(page.items)
            hits.extend(
                SearchHit(
                    kind=self.kind,
                    ref=str(preset.id),
                    title=preset.label,
                    description=preset.description,
                    group=preset.kind,
                )
                for preset in page.items
                if _mentions(query, preset.label, preset.description)
            )
            if page.next is None:
                break
            after = page.next
        return hits


class ExamplePackSource:
    """Example packs, matched on name and description."""

    kind = SearchKind.EXAMPLE_PACK

    def __init__(self, use_case: ListExamplePacks) -> None:
        self._use_case = use_case

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return example packs matching `query`."""
        packs = await self._use_case.handle(ListExamplePacksQuery(), actor)
        return [
            SearchHit(
                kind=self.kind,
                ref=status.summary.id,
                title=status.summary.name,
                description=status.summary.description,
            )
            for status in packs
            if _mentions(query, status.summary.name, status.summary.description)
        ]


class UserSource:
    """Accounts, matched on display name and username, for administrators only.

    `ListUsers` refuses anyone without `identity:user:list`, which the search treats
    as "leave this kind out", so nobody else sees a hint that users are searched.
    """

    kind = SearchKind.USER

    def __init__(self, use_case: ListUsers) -> None:
        self._use_case = use_case

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return accounts matching `query`.

        Only an id, the names, the role and the picture version leave.
        """
        # An instance has few accounts: one page of the most a page holds has them all.
        listings = (
            await self._use_case.handle(ListUsersQuery(limit=MAX_PAGE_ROWS), actor)
        ).items
        return [
            SearchHit(
                kind=self.kind,
                ref=str(listing.user.id),
                title=listing.user.display_name,
                description=f"@{listing.user.username}",
                group=listing.user.role.value,
                avatar_version=(
                    listing.user.avatar.version if listing.user.avatar else None
                ),
            )
            for listing in listings
            if _mentions(query, listing.user.display_name, listing.user.username)
        ]


class SettingSource:
    """Instance settings, matched on title, description and section."""

    kind = SearchKind.SETTING

    def __init__(self, use_case: ListSettings) -> None:
        self._use_case = use_case

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return settings matching `query`."""
        settings = await self._use_case.handle(ListSettingsQuery(), actor)
        return [
            SearchHit(
                kind=self.kind,
                ref=setting.descriptor.key,
                title=setting.descriptor.title,
                description=setting.descriptor.description,
                group=setting.descriptor.group,
                group_title=setting.descriptor.group_title,
            )
            for setting in settings
            if _mentions(
                query,
                setting.descriptor.title,
                setting.descriptor.description,
                setting.descriptor.group_title,
            )
        ]


class PreferenceSource:
    """The person's own preferences, matched like settings; hidden ones never show."""

    kind = SearchKind.PREFERENCE

    def __init__(self, use_case: ListMySettings) -> None:
        self._use_case = use_case

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return the actor's preferences matching `query`."""
        preferences = await self._use_case.handle(ListMySettingsQuery(), actor)
        return [
            SearchHit(
                kind=self.kind,
                ref=preference.descriptor.key,
                title=preference.descriptor.title,
                description=preference.descriptor.description,
                group=preference.descriptor.group,
                group_title=preference.descriptor.group_title,
            )
            for preference in preferences
            if not preference.descriptor.hidden
            and _mentions(
                query,
                preference.descriptor.title,
                preference.descriptor.description,
                preference.descriptor.group_title,
            )
        ]


class ScheduledTaskSource:
    """Scheduled tasks, matched on title and description."""

    kind = SearchKind.SCHEDULED_TASK

    def __init__(self, use_case: ListJobs) -> None:
        self._use_case = use_case

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return scheduled tasks matching `query`."""
        statuses = await self._use_case.handle(
            ListJobsQuery(
                now=datetime.now(UTC), timezone=get_server_settings().time_zone.key
            ),
            actor,
        )
        return [
            SearchHit(
                kind=self.kind,
                ref=status.definition.job_key,
                title=status.definition.title,
                description=status.definition.description,
            )
            for status in statuses
            if _mentions(query, status.definition.title, status.definition.description)
        ]


def get_search_sources(
    nodes: Annotated[ListNodes, Depends(get_list_nodes_use_case)],
    resolver: Annotated[ResolveCollection, Depends(get_resolve_collection_use_case)],
    collections: Annotated[ListCollections, Depends(get_list_collections_use_case)],
    node_types: Annotated[ListNodeTypes, Depends(get_list_node_types_use_case)],
    presets: Annotated[ListPresets, Depends(get_list_presets_use_case)],
    packs: Annotated[ListExamplePacks, Depends(get_list_example_packs_use_case)],
    users: Annotated[ListUsers, Depends(get_list_users_use_case)],
    settings: Annotated[ListSettings, Depends(get_list_settings_use_case)],
    preferences: Annotated[ListMySettings, Depends(get_list_my_settings_use_case)],
    jobs: Annotated[ListJobs, Depends(get_list_jobs_use_case)],
) -> list[SearchSource]:
    """Return one source per kind, each backed by its owner's use case."""
    return [
        ItemSource(nodes, resolver),
        CollectionSource(collections),
        ItemTypeSource(node_types),
        SavedFieldSource(presets),
        ExamplePackSource(packs),
        UserSource(users),
        PreferenceSource(preferences),
        SettingSource(settings),
        ScheduledTaskSource(jobs),
    ]
