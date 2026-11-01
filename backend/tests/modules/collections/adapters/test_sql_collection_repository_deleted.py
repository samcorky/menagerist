import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.domain.collection import Collection
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


async def _shelf(
    repo: SqlAlchemyCollectionRepository,
    name: str,
    *,
    owner: uuid.UUID = ALICE,
    deleted_ago: int | None = None,
) -> Collection:
    collection = Collection.create(name=name, slug=Slug(name), owner_id=owner)
    if deleted_ago is not None:
        collection.deleted_at = datetime.now(UTC) - timedelta(minutes=deleted_ago)
    await repo.add(collection)
    return collection


async def test_deleted_collections_list_newest_first_and_page(
    db_session: AsyncSession,
) -> None:
    """Only the scope's deleted rows, newest deleted first, paged by `after`."""
    repo = SqlAlchemyCollectionRepository(db_session)
    rows = [await _shelf(repo, f"Shelf {i}", deleted_ago=i) for i in range(1, 5)]
    await _shelf(repo, "Live")
    await _shelf(repo, "Theirs", owner=BOB, deleted_ago=1)
    scope = ContentFilter.of(ALICE)

    first = await repo.list_deleted(scope=scope, after=None, limit=3)
    second = await repo.list_deleted(scope=scope, after=first[-1].id, limit=3)
    stale = await repo.list_deleted(scope=scope, after=uuid.uuid7(), limit=3)

    assert [c.id for c in first + second] == [r.id for r in rows]
    assert stale == []
    assert await repo.count_deleted(scope=scope) == 4


async def test_get_deleted_sees_only_deleted_rows_in_scope(
    db_session: AsyncSession,
) -> None:
    """A live collection and another owner's deleted one are not found."""
    repo = SqlAlchemyCollectionRepository(db_session)
    gone = await _shelf(repo, "Gone", deleted_ago=1)
    live = await _shelf(repo, "Live")
    theirs = await _shelf(repo, "Theirs", owner=BOB, deleted_ago=1)
    scope = ContentFilter.of(ALICE)

    assert await repo.get_deleted(gone.id, scope=scope) is not None
    assert await repo.get_deleted(live.id, scope=scope) is None
    assert await repo.get_deleted(theirs.id, scope=scope) is None


async def test_restoring_over_a_live_slug_is_rejected_by_the_index(
    db_session: AsyncSession,
) -> None:
    """The live-slug index backs the use case's check against a race."""
    repo = SqlAlchemyCollectionRepository(db_session)
    gone = await _shelf(repo, "Shelf", deleted_ago=1)
    await repo.add(Collection.create(name="Other", slug=Slug("shelf"), owner_id=ALICE))

    gone.restore()
    with pytest.raises(ConflictError):
        await repo.save(gone)


async def test_deleted_before_lists_oldest_first_for_every_owner(
    db_session: AsyncSession,
) -> None:
    """Collections deleted before the cutoff, any owner, oldest first."""
    repo = SqlAlchemyCollectionRepository(db_session)
    oldest = await _shelf(repo, "Oldest", deleted_ago=3 * 24 * 60)
    older = await _shelf(repo, "Older", owner=BOB, deleted_ago=2 * 24 * 60)
    await _shelf(repo, "Recent", deleted_ago=1)
    await _shelf(repo, "Live")
    cutoff = datetime.now(UTC) - timedelta(days=1)

    first = await repo.list_deleted_before(cutoff, limit=1)
    both = await repo.list_deleted_before(cutoff, limit=10)

    assert [c.id for c in first] == [oldest.id]
    assert [c.id for c in both] == [oldest.id, older.id]
    assert await repo.count_deleted_before(cutoff) == 2
