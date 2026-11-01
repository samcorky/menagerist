import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.adapters.persistence.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from app.modules.collections.adapters.persistence.models import (
    CollectionMemberModel,
    CollectionModel,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _shelf(session: AsyncSession, name: str) -> Collection:
    collection = Collection.create(name=name, slug=Slug(name), owner_id=uuid.uuid7())
    await SqlAlchemyCollectionRepository(session).add(collection)
    return collection


async def _put(session: AsyncSession, collection: Collection, item: uuid.UUID) -> None:
    await SqlAlchemyMembershipRepository(session).add(
        Membership(
            collection_id=collection.id, item_id=item, added_at=datetime.now(UTC)
        )
    )


async def _members(session: AsyncSession) -> set[tuple[uuid.UUID, uuid.UUID]]:
    rows = await session.execute(
        select(CollectionMemberModel.collection_id, CollectionMemberModel.item_id)
    )
    return {(c, i) for c, i in rows}


async def test_purging_a_collection_removes_its_memberships_then_the_row(
    db_session: AsyncSession,
) -> None:
    """The foreign key is respected; another collection's memberships stay."""
    collections = SqlAlchemyCollectionRepository(db_session)
    memberships = SqlAlchemyMembershipRepository(db_session)
    doomed, other = (
        await _shelf(db_session, "Doomed"),
        await _shelf(db_session, "Other"),
    )
    item = uuid.uuid7()
    await _put(db_session, doomed, item)
    await _put(db_session, other, item)
    doomed.soft_delete()
    await collections.save(doomed)

    await memberships.purge_for_collection(doomed.id)
    await collections.purge(doomed.id)

    ids = set((await db_session.execute(select(CollectionModel.id))).scalars())
    assert doomed.id not in ids
    assert other.id in ids
    assert await _members(db_session) == {(other.id, item)}


async def test_purging_an_item_removes_it_from_every_collection(
    db_session: AsyncSession,
) -> None:
    """Live and soft-deleted collections alike lose the row; other items stay."""
    collections = SqlAlchemyCollectionRepository(db_session)
    live, deleted = await _shelf(db_session, "Live"), await _shelf(db_session, "Del")
    gone, kept = uuid.uuid7(), uuid.uuid7()
    await _put(db_session, live, gone)
    await _put(db_session, deleted, gone)
    await _put(db_session, live, kept)
    deleted.soft_delete()
    await collections.save(deleted)

    await SqlAlchemyMembershipRepository(db_session).purge_for_item(gone)

    assert await _members(db_session) == {(live.id, kept)}


async def test_purging_an_unknown_collection_is_a_no_op(
    db_session: AsyncSession,
) -> None:
    """Nothing raises and other rows stay."""
    keeper = await _shelf(db_session, "Keeper")

    await SqlAlchemyMembershipRepository(db_session).purge_for_collection(uuid.uuid7())
    await SqlAlchemyCollectionRepository(db_session).purge(uuid.uuid7())

    ids = set((await db_session.execute(select(CollectionModel.id))).scalars())
    assert keeper.id in ids
