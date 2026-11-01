import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PurgeDeletedCollectionCommand:
    """Request to permanently delete a collection that is in Recently deleted."""

    collection_id: uuid.UUID


class PurgeDeletedCollection(
    CommandHandler[CollectionsUnitOfWork, PurgeDeletedCollectionCommand, None]
):
    """Permanently delete one of the caller's deleted collections and its memberships.

    A live collection, an unknown id and another person's collection are all
    not found. Items stay.
    """

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_PURGE)

    async def _handle(
        self, command: PurgeDeletedCollectionCommand, actor: Actor
    ) -> None:
        """Delete the memberships, then the collection, and commit."""
        async with self._uow as repos:
            collection = await repos.collections.get_deleted(
                command.collection_id, scope=self.scope(actor)
            )
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            self._guard.assert_can_delete(actor, collection.owner_id)
            await repos.memberships.purge_for_collection(collection.id)
            await repos.collections.purge(collection.id)
            await self._uow.commit()
        logger.info("deleted collection purged", collection_id=command.collection_id)
