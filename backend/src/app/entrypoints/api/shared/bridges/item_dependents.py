"""The graph module's view of what other modules hold about an item."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_collections_uow,
)
from app.modules.collections.application.purge_item_memberships import (
    PurgeItemMemberships,
    PurgeItemMembershipsCommand,
)
from app.modules.media.adapters.api.dependencies import get_media_storage
from app.modules.media.adapters.persistence.unit_of_work import (
    build_media_repos,
    create_media_uow,
)
from app.modules.media.application.purge_attachment import (
    PurgeAttachment,
    PurgeAttachmentCommand,
)
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.modules.media.ports.media_storage import MediaStoragePort  # noqa: TC001
from app.platform.database import get_session_factory
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
    from app.modules.media.ports.unit_of_work import MediaRepos, MediaUnitOfWork


class ItemDependentsPurger:
    """Purges an item's memberships and attachments through the System use cases.

    The caller has already confirmed the item is the person's own and deleted.
    An asset another attachment still uses is kept; stored files go only after
    their transaction commits.
    """

    def __init__(
        self,
        *,
        guard: AccessGuard,
        storage: MediaStoragePort,
        collections_uow: Callable[[], CollectionsUnitOfWork],
        media_uow: Callable[[], MediaUnitOfWork],
        media_read: Callable[[], AbstractAsyncContextManager[MediaRepos]],
    ) -> None:
        self._guard = guard
        self._storage = storage
        self._collections_uow = collections_uow
        self._media_uow = media_uow
        self._media_read = media_read

    async def purge_for_item(self, item_id: uuid.UUID) -> None:
        """Remove the item from every collection and delete its attachments."""
        async with self._media_read() as repos:
            # all-users: system clean-up of an item the caller has been checked to own
            attachments = await repos.attachments.list_for_target(
                AttachmentTarget.NODE, item_id, scope=ContentFilter.everyone()
            )
        for attachment in attachments:
            await PurgeAttachment(self._media_uow(), self._guard, self._storage).handle(
                PurgeAttachmentCommand(attachment_id=attachment.id), SYSTEM_ACTOR
            )
        await PurgeItemMemberships(self._collections_uow(), self._guard).handle(
            PurgeItemMembershipsCommand(item_id=item_id), SYSTEM_ACTOR
        )


def get_item_dependents(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ItemDependentsPurger:
    """Return the purger over Postgres."""

    @asynccontextmanager
    async def media_read() -> AsyncIterator[MediaRepos]:
        async with session_factory() as session:
            yield build_media_repos(session)

    return ItemDependentsPurger(
        guard=guard,
        storage=storage,
        collections_uow=lambda: create_collections_uow(session_factory),
        media_uow=lambda: create_media_uow(session_factory),
        media_read=media_read,
    )
