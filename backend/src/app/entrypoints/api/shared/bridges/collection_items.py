"""The collections module's view of graph items: which ids are live, how many match."""

from typing import TYPE_CHECKING, Annotated, Any

import structlog
from fastapi import Depends

from app.entrypoints.api.shared.bridges.collection_conditions import (
    build_search_graph_repos,
)
from app.entrypoints.api.shared.clock import Today, get_today
from app.modules.graph.application.prepare_query import (
    count_matching,
    item_matches,
    utc_today,
)
from app.modules.graph.domain.query import InvalidQueryError
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter

_CHUNK = 1000

logger = structlog.get_logger()


class GraphItemLookup:
    """Reports which item ids are live (non-deleted) and visible in the graph module."""

    def __init__(self, repos: GraphRepos, *, today: Today = utc_today) -> None:
        self._repos = repos
        self._today = today

    async def live_ids(
        self, ids: Sequence[uuid.UUID], scope: ContentFilter
    ) -> set[uuid.UUID]:
        """Return the subset of `ids` that are live items inside `scope`."""
        unique = list(dict.fromkeys(ids))
        live: set[uuid.UUID] = set()
        for start in range(0, len(unique), _CHUNK):
            chunk = unique[start : start + _CHUNK]
            nodes = await self._repos.nodes.list(
                scope=scope,
                after=None,
                limit=len(chunk),
                ids=chunk,
            )
            live.update(node.id for node in nodes)
        return live

    async def count_matching(
        self, definition: Mapping[str, Any], scope: ContentFilter, *, cap: int | None
    ) -> tuple[int, bool]:
        """Return how many items in `scope` match `definition`, and if capped.

        A definition naming fields that were removed matches nothing. One that
        can no longer be read counts as `(0, False)` and is logged.
        """
        try:
            return await count_matching(
                self._repos, definition, scope, cap=cap, today=self._today
            )
        except InvalidQueryError as exc:
            logger.warning("stored collection definition unreadable", error=str(exc))
            return 0, False

    async def matches(
        self, definition: Mapping[str, Any], scope: ContentFilter, item_id: uuid.UUID
    ) -> bool:
        """Return whether the live item `item_id` in `scope` matches `definition`.

        A definition that can no longer be read matches nothing and is logged.
        """
        try:
            return await item_matches(
                self._repos, definition, scope, item_id, today=self._today
            )
        except InvalidQueryError as exc:
            logger.warning("stored collection definition unreadable", error=str(exc))
            return False


async def get_item_lookup(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    today: Annotated[Today, Depends(get_today)],
) -> AsyncIterator[GraphItemLookup]:
    """Yield the item lookup, backed by a read session on the graph tables.

    Smart collections' relative dates resolve in the request's time zone.
    """
    async with session_factory() as session:
        yield GraphItemLookup(build_search_graph_repos(session), today=today)
