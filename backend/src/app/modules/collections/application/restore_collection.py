import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.collection_slugs import slug_is_held
from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.collection import Collection
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ConflictError

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class RestoreCollectionCommand:
    """Request to bring a deleted collection back."""

    collection_id: uuid.UUID


class RestoreCollection(
    CommandHandler[CollectionsUnitOfWork, RestoreCollectionCommand, Collection]
):
    """Clear a collection's deletion mark; memberships and definition are as left.

    The only uniqueness rule is the slug per owner among live collections, so a
    live collection that took the slug since is a 409 (no automatic renaming).
    """

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_WRITE)

    async def _handle(
        self, command: RestoreCollectionCommand, actor: Actor
    ) -> Collection:
        """Restore the collection and commit.

        Raises:
            CollectionNotFoundError: If it is not in the caller's Recently deleted list.
            ConflictError: If a live collection of the owner now has its slug.
        """
        async with self._uow as repos:
            scope = self.scope(actor)
            collection = await repos.collections.get_deleted(
                command.collection_id, scope=scope
            )
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            self._guard.assert_can_delete(actor, collection.owner_id)
            if await slug_is_held(repos.collections, collection.slug.value, scope):
                raise ConflictError(
                    f"A collection with slug '{collection.slug}' already exists. "
                    + "Rename or delete it, then try again."
                )
            collection.restore()
            await repos.collections.save(collection)
            await self._uow.commit()
        logger.info("collection restored", collection_id=command.collection_id)
        return collection
