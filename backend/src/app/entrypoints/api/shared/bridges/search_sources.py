"""The search module's view of the modules that own what it finds.

Each source asks the owner's own use case, so the owner keeps its permission
checks, content filtering and accent folding. A source the actor may not use
raises `ForbiddenError` from that use case, which the search treats as "leave
this kind out".
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.collections.adapters.api.dependencies import (
    get_list_collections_use_case,
)
from app.modules.collections.application.list_collections import (
    ListCollections,
    ListCollectionsQuery,
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
from app.modules.scheduling.adapters.api.dependencies import get_list_jobs_use_case
from app.modules.scheduling.application.list_jobs import ListJobs, ListJobsQuery
from app.modules.search.domain.search_hit import SearchHit, SearchKind
from app.modules.settings.adapters.api.dependencies import get_list_settings_use_case
from app.modules.settings.application.list_settings import (
    ListSettings,
    ListSettingsQuery,
)
from app.platform.config import get_scheduler_settings
from app.shared_kernel.text import fold

if TYPE_CHECKING:
    from app.modules.search.ports.search_source import SearchSource
    from app.shared_kernel.actor import Actor

# Item types and the two registries are small and have no text filter of their own,
# so they are read whole, a page at a time, and filtered here.
_TYPE_PAGE = 100
_TYPE_CAP = 10_000


def _mentions(query: str, *texts: str | None) -> bool:
    needle = fold(query.strip())
    return any(needle in fold(text) for text in texts if text)


class ItemSource:
    """Items, matched by the graph module on name, description and field values."""

    kind = SearchKind.ITEM

    def __init__(self, use_case: ListNodes) -> None:
        self._use_case = use_case

    async def find(self, query: str, limit: int, actor: Actor) -> list[SearchHit]:
        """Return items matching `query`."""
        result = await self._use_case.handle(
            ListNodesQuery(q=query, limit=limit), actor
        )
        return [
            SearchHit(
                kind=self.kind,
                ref=str(node.id),
                title=node.name,
                description=node.description,
                group=node.type,
                attributes=node.attributes,
            )
            for node in result.items
        ]


class CollectionSource:
    """Collections, matched by the collections module on name and description."""

    kind = SearchKind.COLLECTION

    def __init__(self, use_case: ListCollections) -> None:
        self._use_case = use_case

    async def find(self, query: str, limit: int, actor: Actor) -> list[SearchHit]:
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

    async def find(self, query: str, limit: int, actor: Actor) -> list[SearchHit]:
        """Return item types matching `query`."""
        hits: list[SearchHit] = []
        after = None
        seen = 0
        while seen < _TYPE_CAP:
            page = await self._use_case.handle(
                ListNodeTypesQuery(after=after, limit=_TYPE_PAGE), actor
            )
            seen += len(page)
            hits.extend(
                SearchHit(
                    kind=self.kind,
                    ref=str(node_type.slug),
                    title=node_type.label,
                    description=node_type.description,
                )
                for node_type in page
                if _mentions(query, node_type.label, str(node_type.slug))
            )
            if len(page) < _TYPE_PAGE:
                break
            after = page[-1].id
        return hits


class SettingSource:
    """Instance settings, matched on title, description and section."""

    kind = SearchKind.SETTING

    def __init__(self, use_case: ListSettings) -> None:
        self._use_case = use_case

    async def find(self, query: str, limit: int, actor: Actor) -> list[SearchHit]:
        """Return settings matching `query`."""
        settings = await self._use_case.handle(ListSettingsQuery(), actor)
        return [
            SearchHit(
                kind=self.kind,
                ref=setting.descriptor.key,
                title=setting.descriptor.title,
                description=setting.descriptor.description,
                group=setting.descriptor.group,
            )
            for setting in settings
            if _mentions(
                query,
                setting.descriptor.title,
                setting.descriptor.description,
                setting.descriptor.group.replace("_", " "),
            )
        ]


class ScheduledTaskSource:
    """Scheduled tasks, matched on title and description."""

    kind = SearchKind.SCHEDULED_TASK

    def __init__(self, use_case: ListJobs) -> None:
        self._use_case = use_case

    async def find(self, query: str, limit: int, actor: Actor) -> list[SearchHit]:
        """Return scheduled tasks matching `query`."""
        statuses = await self._use_case.handle(
            ListJobsQuery(
                now=datetime.now(UTC), timezone=get_scheduler_settings().timezone.key
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
    collections: Annotated[ListCollections, Depends(get_list_collections_use_case)],
    node_types: Annotated[ListNodeTypes, Depends(get_list_node_types_use_case)],
    settings: Annotated[ListSettings, Depends(get_list_settings_use_case)],
    jobs: Annotated[ListJobs, Depends(get_list_jobs_use_case)],
) -> list[SearchSource]:
    """Return one source per kind, each backed by its owner's use case."""
    return [
        ItemSource(nodes),
        CollectionSource(collections),
        ItemTypeSource(node_types),
        SettingSource(settings),
        ScheduledTaskSource(jobs),
    ]
