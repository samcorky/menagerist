import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.adapters.persistence.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from app.modules.collections.adapters.persistence.models import CollectionMemberModel
from app.modules.collections.domain.collection import Collection, Membership
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _shelf(session: AsyncSession, name: str) -> Collection:
    """Store a collection so memberships can reference it."""
    collection = Collection.create(name=name, slug=Slug(name), owner_id=uuid.uuid7())
    await SqlAlchemyCollectionRepository(session).add(collection)
    return collection


def _membership(collection_id: uuid.UUID, item_id: uuid.UUID) -> Membership:
    return Membership(
        collection_id=collection_id, item_id=item_id, added_at=datetime.now(UTC)
    )


async def test_add_and_lookup_both_ways(db_session: AsyncSession) -> None:
    """Memberships are found from the collection and from the item."""
    repo = SqlAlchemyMembershipRepository(db_session)
    shelf_a, shelf_b = await _shelf(db_session, "A"), await _shelf(db_session, "B")
    item_1, item_2 = uuid.uuid7(), uuid.uuid7()
    await repo.add(_membership(shelf_a.id, item_1))
    await repo.add(_membership(shelf_a.id, item_2))
    await repo.add(_membership(shelf_b.id, item_1))

    assert await repo.item_ids(shelf_a.id) == {item_1, item_2}
    assert await repo.item_ids(shelf_b.id) == {item_1}
    assert await repo.collection_ids_for(item_1) == {shelf_a.id, shelf_b.id}
    assert await repo.collection_ids_for(item_2) == {shelf_a.id}
    assert await repo.item_ids(uuid.uuid7()) == set()
    assert await repo.collection_ids_for(uuid.uuid7()) == set()


async def test_adding_twice_stores_one_row(db_session: AsyncSession) -> None:
    """A repeated add raises nothing and leaves a single row."""
    repo = SqlAlchemyMembershipRepository(db_session)
    shelf, item = await _shelf(db_session, "A"), uuid.uuid7()
    await repo.add(_membership(shelf.id, item))
    await repo.add(_membership(shelf.id, item))

    count = await db_session.scalar(
        select(func.count()).select_from(CollectionMemberModel)
    )

    assert count == 1


async def test_remove_drops_only_the_given_pair(db_session: AsyncSession) -> None:
    """Removal leaves other pairs alone; removing a missing pair is a no-op."""
    repo = SqlAlchemyMembershipRepository(db_session)
    shelf_a, shelf_b = await _shelf(db_session, "A"), await _shelf(db_session, "B")
    item_1, item_2 = uuid.uuid7(), uuid.uuid7()
    for pair in ((shelf_a.id, item_1), (shelf_a.id, item_2), (shelf_b.id, item_1)):
        await repo.add(_membership(*pair))

    await repo.remove(shelf_a.id, item_1)
    await repo.remove(shelf_a.id, uuid.uuid7())

    assert await repo.item_ids(shelf_a.id) == {item_2}
    assert await repo.collection_ids_for(item_1) == {shelf_b.id}


async def test_soft_deleting_a_collection_keeps_its_memberships(
    db_session: AsyncSession,
) -> None:
    """Membership rows survive the soft delete of their collection."""
    collections = SqlAlchemyCollectionRepository(db_session)
    repo = SqlAlchemyMembershipRepository(db_session)
    shelf, item = await _shelf(db_session, "A"), uuid.uuid7()
    await repo.add(_membership(shelf.id, item))

    shelf.soft_delete()
    await collections.save(shelf)

    assert await repo.item_ids(shelf.id) == {item}
    assert await repo.collection_ids_for(item) == {shelf.id}
