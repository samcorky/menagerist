"""The graph module's view of copying an item's media and collections."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.attach_target_access import (
    GraphAttachTargetAccess,
)
from app.entrypoints.api.shared.bridges.collection_items import GraphItemLookup
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_collections_uow,
)
from app.modules.collections.application.copy_item_memberships import (
    CopyItemMemberships,
    CopyItemMembershipsCommand,
)
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.media.adapters.api.dependencies import get_media_storage
from app.modules.media.adapters.persistence.unit_of_work import create_media_uow
from app.modules.media.application.copy_item_media import (
    CopyItemMedia,
    CopyItemMediaCommand,
)
from app.modules.media.ports.media_storage import MediaStoragePort  # noqa: TC001
from app.platform.database import get_session_factory
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.collections.ports.item_lookup import ItemLookup
    from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
    from app.modules.media.ports.attach_target_access import AttachTargetAccess
    from app.modules.media.ports.unit_of_work import MediaUnitOfWork
    from app.shared_kernel.actor import Actor


class ItemCompanionCopier:
    """Copies media and collections through the media and collections use cases.

    Each runs in its own transaction after the duplicate has committed, with the
    caller's own actor, so the usual permissions apply to every step.
    """

    def __init__(
        self,
        *,
        guard: AccessGuard,
        storage: MediaStoragePort,
        collections_uow: Callable[[], CollectionsUnitOfWork],
        media_uow: Callable[[], MediaUnitOfWork],
        items: Callable[[], AbstractAsyncContextManager[ItemLookup]],
        targets: Callable[[], AbstractAsyncContextManager[AttachTargetAccess]],
    ) -> None:
        self._guard = guard
        self._storage = storage
        self._items = items
        self._targets = targets
        self._collections_uow = collections_uow
        self._media_uow = media_uow

    async def copy_media(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        attachments: bool,
        cover: bool,
        actor: Actor,
    ) -> None:
        """Copy the source's chosen media files onto the target."""
        async with self._targets() as targets:
            await CopyItemMedia(
                self._media_uow(), self._guard, self._storage, targets
            ).handle(
                CopyItemMediaCommand(
                    source_id=source_id,
                    target_id=target_id,
                    attachments=attachments,
                    cover=cover,
                ),
                actor,
            )

    async def copy_collections(
        self, source_id: uuid.UUID, target_id: uuid.UUID, *, actor: Actor
    ) -> None:
        """Add the target to the source's manual collections."""
        async with self._items() as items:
            await CopyItemMemberships(
                self._collections_uow(), self._guard, items
            ).handle(
                CopyItemMembershipsCommand(source_id=source_id, target_id=target_id),
                actor,
            )


def get_item_companions(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ItemCompanionCopier:
    """Return the copier over Postgres."""

    @asynccontextmanager
    async def items() -> AsyncIterator[ItemLookup]:
        async with session_factory() as session:
            yield GraphItemLookup(build_graph_repos(session))

    @asynccontextmanager
    async def targets() -> AsyncIterator[AttachTargetAccess]:
        async with session_factory() as session:
            yield GraphAttachTargetAccess(build_graph_repos(session))

    return ItemCompanionCopier(
        guard=guard,
        storage=storage,
        collections_uow=lambda: create_collections_uow(session_factory),
        media_uow=lambda: create_media_uow(session_factory),
        items=items,
        targets=targets,
    )
