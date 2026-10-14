from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_immutable_unaccent_strips_accents(db_session: AsyncSession) -> None:
    """The wrapper resolves `unaccent` and strips diacritics."""
    result = await db_session.execute(text("SELECT immutable_unaccent('Café Crème')"))
    assert result.scalar_one() == "Cafe Creme"


async def test_immutable_unaccent_is_immutable(db_session: AsyncSession) -> None:
    """Only an IMMUTABLE function can back an expression index."""
    result = await db_session.execute(
        text(
            "SELECT provolatile::text FROM pg_proc WHERE proname = 'immutable_unaccent'"
        )
    )
    assert result.scalar_one() == "i"


async def test_name_trigram_index_serves_unaccented_ilike(
    db_session: AsyncSession,
) -> None:
    """A forced plan for an unaccented ILIKE on name uses the trigram index."""
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    result = await db_session.execute(
        text(
            "EXPLAIN SELECT id FROM nodes WHERE immutable_unaccent(name) ILIKE '%cafe%'"
        )
    )
    plan = "\n".join(row[0] for row in result)
    assert "ix_nodes_name_trgm" in plan
