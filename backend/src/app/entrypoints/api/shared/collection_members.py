"""The graph module's view of collections: which items are on a collection."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
)
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.collections.ports.unit_of_work import CollectionsRepos


class CollectionsMembers:
    """Reads the item ids on a collection from the collections module."""

    def __init__(self, repos: CollectionsRepos) -> None:
        self._repos = repos

    async def item_ids(self, collection_id: uuid.UUID) -> set[uuid.UUID] | None:
        """Return the item ids on the collection, or `None` if missing or deleted.

        Membership rows outlive deleted items; filtering them is the item side's job.
        """
        if await self._repos.collections.get(collection_id) is None:
            return None
        return await self._repos.memberships.item_ids(collection_id)


async def get_collection_members(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[CollectionsMembers]:
    """Yield the members source, backed by a read session on the collections tables."""
    async with session_factory() as session:
        yield CollectionsMembers(build_collections_repos(session))
