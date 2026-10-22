import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.guarded import GuardedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ResolveCollectionQuery:
    """Request to turn a path segment, a collection id or slug, into an id."""

    id_or_slug: str


class ResolveCollection(
    GuardedQueryHandler[CollectionsRepos, ResolveCollectionQuery, uuid.UUID]
):
    """Resolve an id or a slug to a collection id within the caller's scope."""

    access: ClassVar[Access] = Content()

    async def _handle(self, query: ResolveCollectionQuery, actor: Actor) -> uuid.UUID:
        """Return the id: a UUID passes through; a slug is looked up.

        Slugs are never UUID-shaped, so the two forms cannot be confused. A slug
        that is unknown, deleted or another owner's is not found.

        Raises:
            CollectionNotFoundError: If no such collection is visible.
        """
        try:
            return uuid.UUID(query.id_or_slug)
        except ValueError:
            pass
        collection = await self._repos.collections.get_by_slug(
            query.id_or_slug, scope=self.scope(actor)
        )
        if collection is None:
            raise CollectionNotFoundError(f"Collection {query.id_or_slug} not found")
        return collection.id
