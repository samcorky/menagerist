import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.graph.adapters.persistence.edge_type_repository import (
    SqlAlchemyEdgeTypeRepository,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.paging import PageRequest, SortOrder

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_slug_can_be_reused_after_soft_delete(db_session: AsyncSession) -> None:
    """A soft-deleted edge type stops reserving its slug."""
    repository = SqlAlchemyEdgeTypeRepository(db_session)
    first = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="signed-by", label="Signed by"
    )
    await repository.add(first)
    first.soft_delete()
    await repository.save(first)

    second = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="signed-by", label="Signed by again"
    )
    await repository.add(second)

    live = await repository.get_by_slug("signed-by", scope=ContentFilter.everyone())
    assert live is not None
    assert live.id == second.id


async def test_item_type_limits_are_stored_and_read_back(
    db_session: AsyncSession,
) -> None:
    """The two lists survive a round trip; a type without them has none."""
    repository = SqlAlchemyEdgeTypeRepository(db_session)
    limited = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id,
        slug="signed-by",
        label="Signed by",
        source_types=["book", "comic"],
        target_types=["person"],
    )
    open_ended = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="related", label="Related"
    )
    await repository.add(limited)
    await repository.add(open_ended)
    limited.update(target_types=[])
    await repository.save(limited)

    scope = ContentFilter.everyone()
    first = await repository.get_by_slug("signed-by", scope=scope)
    second = await repository.get_by_slug("related", scope=scope)
    assert first is not None
    assert second is not None
    assert (first.source_types, first.target_types) == (("book", "comic"), ())
    assert (second.source_types, second.target_types) == ((), ())


async def test_live_edge_types_cannot_share_a_slug(db_session: AsyncSession) -> None:
    """The index backs the use case's check: two live types cannot share a slug."""
    repository = SqlAlchemyEdgeTypeRepository(db_session)
    await repository.add(
        EdgeType.create(owner_id=SYSTEM_ACTOR.id, slug="signed-by", label="Signed by")
    )

    with pytest.raises(IntegrityError):
        await repository.add(
            EdgeType.create(
                owner_id=SYSTEM_ACTOR.id, slug="signed-by", label="Duplicate"
            )
        )


@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", [None, "slug", "label", "created_at", "updated_at"])
async def test_list_cursors_visit_every_edge_type_once_in_order(
    db_session: AsyncSession, sort: str | None, order: SortOrder
) -> None:
    """Following `next` never repeats a type or skips one, whatever the sort."""
    repository = SqlAlchemyEdgeTypeRepository(db_session)
    owner = uuid.uuid7()
    for slug, label in [("b", "B"), ("a", "a"), ("c", "C"), ("d", "b"), ("e", "A")]:
        await repository.add(EdgeType.create(owner_id=owner, slug=slug, label=label))
    scope = ContentFilter.everyone()
    everything = (
        await repository.list(
            scope=scope, page=PageRequest(sort=sort, order=order, limit=100)
        )
    ).items

    seen: list[uuid.UUID] = []
    request = PageRequest(sort=sort, order=order, limit=2)
    while True:
        page = await repository.list(scope=scope, page=request)
        seen.extend(t.id for t in page.items)
        if page.next is None:
            break
        request = PageRequest(after=page.next, sort=sort, order=order, limit=2)

    assert seen == [t.id for t in everything]
    assert len(set(seen)) == 5
