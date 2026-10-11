"""The collections module's view of graph items: which of a set of ids are live."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.access_scope import AccessScope

_CHUNK = 1000


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


async def get_item_lookup(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[GraphItemLookup]:
    """Yield the item lookup, backed by a read session on the graph tables."""
    async with session_factory() as session:
        yield GraphItemLookup(build_graph_repos(session))
