from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.modules.collections.adapters.persistence.models import (
    CollectionMemberModel,
    CollectionModel,
)
from app.platform.orm_mixins import owned_by

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.collections.domain.collection import Membership
    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


class SqlAlchemyMembershipRepository:
    """Postgres-backed `MembershipRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, membership: Membership) -> None:
        """Add a membership; adding an existing pair leaves one stored."""
        logger.debug(
            "adding membership",
            collection_id=membership.collection_id,
            item_id=membership.item_id,
        )
        stmt = (
            insert(CollectionMemberModel)
            .values(
                collection_id=membership.collection_id,
                item_id=membership.item_id,
                added_at=membership.added_at,
            )
            .on_conflict_do_nothing(index_elements=["collection_id", "item_id"])
        )
        await self._session.execute(stmt)

    async def remove(self, collection_id: uuid.UUID, item_id: uuid.UUID) -> None:
        """Remove a membership; a missing pair is a no-op."""
        await self._session.execute(
            delete(CollectionMemberModel).where(
                CollectionMemberModel.collection_id == collection_id,
                CollectionMemberModel.item_id == item_id,
            )
        )

    async def item_ids(
        self, collection_id: uuid.UUID, *, scope: ContentFilter
    ) -> set[uuid.UUID]:
        """Return the item ids on `collection_id`; empty unless it is in `scope`."""
        stmt = (
            select(CollectionMemberModel.item_id)
            .join(
                CollectionModel,
                CollectionModel.id == CollectionMemberModel.collection_id,
            )
            .where(
                CollectionMemberModel.collection_id == collection_id,
                owned_by(CollectionModel, scope.user_id),
            )
        )
        return set((await self._session.execute(stmt)).scalars())

    async def collection_ids_for(
        self, item_id: uuid.UUID, *, scope: ContentFilter
    ) -> set[uuid.UUID]:
        """Return the ids of the collections in `scope` holding `item_id`.

        Soft-deleted collections are included: callers filter on liveness.
        """
        stmt = (
            select(CollectionMemberModel.collection_id)
            .join(
                CollectionModel,
                CollectionModel.id == CollectionMemberModel.collection_id,
            )
            .where(
                CollectionMemberModel.item_id == item_id,
                owned_by(CollectionModel, scope.user_id),
            )
        )
        return set((await self._session.execute(stmt)).scalars())
