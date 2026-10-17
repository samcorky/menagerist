"""The collections module's view of graph items: which ids are live, how many match."""

from typing import TYPE_CHECKING, Annotated, Any

import structlog
from fastapi import Depends

from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.application.prepare_query import count_matching
from app.modules.graph.domain.query import InvalidQueryError
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.access_scope import AccessScope

_CHUNK = 1000

logger = structlog.get_logger()


class GraphItemLookup:
    """Reports which item ids are live (non-deleted) and visible in the graph module."""

    def __init__(self, repos: GraphRepos) -> None:
        self._repos = repos

    async def live_ids(
        self, ids: Sequence[uuid.UUID], scope: AccessScope
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
        self, definition: Mapping[str, Any], scope: AccessScope, *, cap: int | None
    ) -> tuple[int, bool]:
        """Return how many items in `scope` match `definition`, and if capped.

        A definition naming fields that were removed matches nothing. One that
        can no longer be read counts as `(0, False)` and is logged.
        """
        try:
            return await count_matching(self._repos, definition, scope, cap=cap)
        except InvalidQueryError as exc:
            logger.warning("stored collection definition unreadable", error=str(exc))
            return 0, False


async def get_item_lookup(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[GraphItemLookup]:
    """Yield the item lookup, backed by a read session on the graph tables."""
    async with session_factory() as session:
        yield GraphItemLookup(build_graph_repos(session))
