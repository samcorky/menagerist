import json
import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.query import ResolvedQuery, parse_query
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select

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


class _Capture:
    """A session stand-in that records the statement instead of running it."""

    def __init__(self) -> None:
        self.statement: Select[Any] | None = None

    async def execute(self, statement: Select[Any]) -> _Capture:
        self.statement = statement
        return self

    def all(self) -> list[Any]:
        return []


async def test_per_item_field_condition_uses_the_extra_schema_index(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A selective per-item condition is answered from the overlay index."""
    # Lets the containment operands render inline for EXPLAIN.
    monkeypatch.setattr(
        JSONB,
        "literal_processor",
        lambda _self, _dialect: lambda v: f"'{json.dumps(v)}'::jsonb",
        raising=False,
    )
    await db_session.execute(
        text(
            """
            INSERT INTO nodes (id, owner_id, name, tags, attributes, favourite,
                               created_at, updated_at, type, extra_schema)
            SELECT gen_random_uuid(), :owner, 'Item ' || n, '[]'::jsonb, '{}'::jsonb,
                   false, to_timestamp(1700000000 + n), to_timestamp(1700000000 + n),
                   NULL,
                   CASE WHEN n % 5000 = 0 THEN jsonb_build_object(
                       'properties', jsonb_build_object(
                           'signed', jsonb_build_object(
                               'x-menagerist', jsonb_build_object('kind', 'boolean'))))
                   END
            FROM generate_series(1, 20000) AS n
            """
        ),
        {"owner": uuid.UUID(int=303)},
    )
    await db_session.execute(text("ANALYZE nodes"))
    query = parse_query(
        {
            "v": 1,
            "where": {
                "op": "and",
                "children": [
                    {
                        "kind": "field",
                        "field_kind": "boolean",
                        "key": "signed",
                        "op": "=",
                        "value": True,
                    }
                ],
            },
        }
    )
    resolved = ResolvedQuery(
        query=query,
        field_kinds=resolve_fields(query, {}).kinds,
        search_exclusions={},
        today=date(2026, 10, 16),
    )
    capture = _Capture()
    await SqlAlchemyNodeRepository(capture).search(  # type: ignore[arg-type]
        scope=ContentFilter.of(uuid.UUID(int=303)),
        resolved=resolved,
        after=None,
        limit=51,
    )
    assert capture.statement is not None
    sql = str(
        capture.statement.compile(
            dialect=db_session.get_bind().dialect,
            compile_kwargs={"literal_binds": True},
        )
    )
    result = await db_session.execute(text(f"EXPLAIN {sql}"))
    plan = "\n".join(row[0] for row in result)
    assert "Bitmap Index Scan on ix_nodes_extra_schema_gin" in plan, plan
