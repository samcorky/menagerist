import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.paging import PageRequest, SortOrder

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


async def _node(
    repo: SqlAlchemyNodeRepository,
    name: str,
    *,
    owner: uuid.UUID = ALICE,
    deleted_ago: int | None = None,
) -> Node:
    node = Node.create(owner_id=owner, name=name)
    if deleted_ago is not None:
        node.deleted_at = datetime.now(UTC) - timedelta(minutes=deleted_ago)
    await repo.add(node)
    return node


async def test_deleted_rows_list_newest_first_and_page_by_last_id(
    db_session: AsyncSession,
) -> None:
    """Only the scope's deleted rows, newest deleted first, paged by `after`."""
    repo = SqlAlchemyNodeRepository(db_session)
    rows = [await _node(repo, str(i), deleted_ago=i) for i in range(1, 6)]
    await _node(repo, "live")
    await _node(repo, "theirs", owner=BOB, deleted_ago=1)
    scope = ContentFilter.of(ALICE)

    pages = []
    request = PageRequest(sort="deleted_at", order=SortOrder.DESC, limit=2)
    while True:
        page = await repo.list_deleted(scope=scope, page=request)
        pages.append(page)
        if page.next is None:
            break
        request = PageRequest(
            after=page.next, sort="deleted_at", order=SortOrder.DESC, limit=2
        )

    assert [n.id for page in pages for n in page.items] == [r.id for r in rows]
    assert len(pages) == 3
    assert await repo.count_deleted(scope=scope) == 5
    assert await repo.count_deleted(scope=ContentFilter.of(BOB)) == 1


async def test_get_deleted_sees_only_deleted_rows_in_scope(
    db_session: AsyncSession,
) -> None:
    """A live row and another owner's deleted row are not found."""
    repo = SqlAlchemyNodeRepository(db_session)
    gone = await _node(repo, "gone", deleted_ago=1)
    live = await _node(repo, "live")
    theirs = await _node(repo, "theirs", owner=BOB, deleted_ago=1)
    scope = ContentFilter.of(ALICE)

    found = await repo.get_deleted(gone.id, scope=scope)
    assert found is not None
    assert found.deleted_at is not None
    assert await repo.get_deleted(live.id, scope=scope) is None
    assert await repo.get_deleted(theirs.id, scope=scope) is None
    assert await repo.get_deleted(theirs.id, scope=ContentFilter.everyone())


async def test_restoring_makes_the_row_live_again(db_session: AsyncSession) -> None:
    """Saving a restored node clears the mark in the table."""
    repo = SqlAlchemyNodeRepository(db_session)
    node = await _node(repo, "Alien", deleted_ago=1)
    scope = ContentFilter.of(ALICE)

    node.restore()
    await repo.save(node)

    assert await repo.get_deleted(node.id, scope=scope) is None
    assert await repo.get(node.id, scope=scope) is not None


async def test_deleted_before_lists_oldest_first_for_every_owner(
    db_session: AsyncSession,
) -> None:
    """Rows deleted before the cutoff, any owner, oldest first, bounded by limit."""
    repo = SqlAlchemyNodeRepository(db_session)
    oldest = await _node(repo, "oldest", deleted_ago=3 * 24 * 60)
    older = await _node(repo, "older", owner=BOB, deleted_ago=2 * 24 * 60)
    await _node(repo, "recent", deleted_ago=1)
    await _node(repo, "live")
    cutoff = datetime.now(UTC) - timedelta(days=1)

    first = await repo.list_deleted_before(cutoff, limit=1)
    both = await repo.list_deleted_before(cutoff, limit=10)

    assert [n.id for n in first] == [oldest.id]
    assert [n.id for n in both] == [oldest.id, older.id]
    assert await repo.count_deleted_before(cutoff) == 2
    assert await repo.count_deleted_before(oldest.deleted_at) == 0  # type: ignore[arg-type]


async def test_deleted_rows_filter_by_name_or_type_with_q(
    db_session: AsyncSession,
) -> None:
    """`q` reads the name and the type, ignoring case and accents, in scope."""
    repo = SqlAlchemyNodeRepository(db_session)
    scope = ContentFilter.of(ALICE)
    by_name = await _node(repo, "Café table", deleted_ago=1)
    typed = Node.create(owner_id=ALICE, name="Plain", type="cafe-menu")
    typed.deleted_at = datetime.now(UTC) - timedelta(minutes=2)
    await repo.add(typed)
    await _node(repo, "Spoon", deleted_ago=3)
    await _node(repo, "Café theirs", owner=BOB, deleted_ago=1)
    await _node(repo, "Café live")

    found = await repo.list_deleted(scope=scope, page=PageRequest(limit=10), q="CAFE")

    assert {n.id for n in found.items} == {by_name.id, typed.id}
