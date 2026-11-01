import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


async def test_deleted_before_lists_oldest_first_for_every_owner(
    db_session: AsyncSession,
) -> None:
    """Connections deleted before the cutoff, any owner, oldest first."""
    nodes = SqlAlchemyNodeRepository(db_session)
    edges = SqlAlchemyEdgeRepository(db_session)
    a, b = (Node.create(owner_id=ALICE, name=n, type=None) for n in "ab")
    await nodes.add(a)
    await nodes.add(b)
    made: list[Edge] = []
    for owner, days in ((ALICE, 3), (BOB, 2), (ALICE, None)):
        edge = Edge.create(owner_id=owner, source_id=a.id, target_id=b.id, type="knows")
        if days is not None:
            edge.deleted_at = datetime.now(UTC) - timedelta(days=days)
        await edges.add(edge)
        made.append(edge)
    recent = Edge.create(owner_id=ALICE, source_id=b.id, target_id=a.id, type="knows")
    recent.deleted_at = datetime.now(UTC) - timedelta(minutes=1)
    await edges.add(recent)
    cutoff = datetime.now(UTC) - timedelta(days=1)

    first = await edges.list_deleted_before(cutoff, limit=1)
    both = await edges.list_deleted_before(cutoff, limit=10)

    assert [e.id for e in first] == [made[0].id]
    assert [e.id for e in both] == [made[0].id, made[1].id]
    assert await edges.count_deleted_before(cutoff) == 2
