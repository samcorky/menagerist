from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.graph.adapters.persistence.edge_type_repository import (
    SqlAlchemyEdgeTypeRepository,
)
from app.modules.graph.domain.edge_type import EdgeType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_slug_can_be_reused_after_soft_delete(db_session: AsyncSession) -> None:
    """A soft-deleted edge type stops reserving its slug."""
    repository = SqlAlchemyEdgeTypeRepository(db_session)
    first = EdgeType.create(slug="signed-by", label="Signed by")
    await repository.add(first)
    first.soft_delete()
    await repository.save(first)

    second = EdgeType.create(slug="signed-by", label="Signed by again")
    await repository.add(second)

    live = await repository.get_by_slug("signed-by")
    assert live is not None
    assert live.id == second.id


async def test_live_edge_types_cannot_share_a_slug(db_session: AsyncSession) -> None:
    """The index backs the use case's check: two live types cannot share a slug."""
    repository = SqlAlchemyEdgeTypeRepository(db_session)
    await repository.add(EdgeType.create(slug="signed-by", label="Signed by"))

    with pytest.raises(IntegrityError):
        await repository.add(EdgeType.create(slug="signed-by", label="Duplicate"))
