"""The graph module's view of collections: what a collection holds."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
)
from app.modules.collections.domain.collection import CollectionKind
from app.modules.graph.ports.collection_members import (
    CollectionSource,
    ManualSource,
    SmartSource,
)
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.collections.ports.unit_of_work import CollectionsRepos
    from app.shared_kernel.content_filter import ContentFilter


class CollectionsMembers:
    """Reads what a collection holds from the collections module."""

    def __init__(self, repos: CollectionsRepos) -> None:
        self._repos = repos

    async def resolve(
        self, collection_id: uuid.UUID, scope: ContentFilter
    ) -> CollectionSource | None:
        """Return what the collection holds, or `None` if not visible in `scope`.

        A collection that is missing, deleted or owned by someone else is `None`.
        A smart collection yields its definition; a manual one its item ids.

        Membership rows outlive deleted items; filtering them is the item side's job.
        """
        collection = await self._repos.collections.get(collection_id, scope=scope)
        if collection is None:
            return None
        if collection.kind is CollectionKind.DYNAMIC:
            # A smart collection always has a definition; none would match nothing.
            return SmartSource(definition=collection.definition or {})
        ids = await self._repos.memberships.item_ids(collection_id, scope=scope)
        return ManualSource(ids=frozenset(ids))


async def get_collection_members(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[CollectionsMembers]:
    """Yield the members source, backed by a read session on the collections tables."""
    async with session_factory() as session:
        yield CollectionsMembers(build_collections_repos(session))
