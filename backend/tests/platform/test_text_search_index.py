import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.adapters.persistence.search_sql import _UNACCENT_TO_JSON_ESCAPED
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.query import ResolvedQuery, parse_query
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select

pytestmark = pytest.mark.integration

OWNER = uuid.UUID(int=302)


class _Capture:
    """A session stand-in that records the statement instead of running it."""

    def __init__(self) -> None:
        self.statement: Select[Any] | None = None

    async def execute(self, statement: Select[Any]) -> _Capture:
        self.statement = statement
        return self

    def all(self) -> list[Any]:
        return []


async def _plan(
    db_session: AsyncSession, q: str, kind: dict[str, Any] | None = None
) -> str:
    condition = kind or {"kind": "text", "q": q}
    query = parse_query({"v": 1, "where": {"op": "and", "children": [condition]}})
    resolved = ResolvedQuery(
        query=query,
        field_kinds=resolve_fields(query, {}).kinds,
        search_exclusions={},
        today=date(2026, 10, 15),
    )
    capture = _Capture()
    await SqlAlchemyNodeRepository(capture).search(  # type: ignore[arg-type]
        scope=ContentFilter.of(OWNER), resolved=resolved, after=None, limit=51
    )
    assert capture.statement is not None
    sql = str(
        capture.statement.compile(
            dialect=db_session.get_bind().dialect,
            compile_kwargs={"literal_binds": True},
        )
    )
    result = await db_session.execute(text(f"EXPLAIN {sql}"))
    return "\n".join(row[0] for row in result)


async def test_selective_text_search_uses_the_trigram_indexes(
    db_session: AsyncSession,
) -> None:
    """A selective text query is answered from the trigram indexes, not a scan."""
    await db_session.execute(
        text(
            """
            INSERT INTO nodes (id, owner_id, name, tags, attributes, favourite,
                               created_at, updated_at, type)
            SELECT gen_random_uuid(), :owner, 'Item ' || n, '[]'::jsonb,
                   jsonb_build_object(
                       'notes', 'filler text ' || n || ' about nothing',
                       'extra', CASE WHEN n % 5000 = 0
                                THEN 'zebrafish ' || n ELSE 'plain' END),
                   false, to_timestamp(1700000000 + n),
                   to_timestamp(1700000000 + n), 'film'
            FROM generate_series(1, 20000) AS n
            """
        ),
        {"owner": OWNER},
    )
    await db_session.execute(text("ANALYZE nodes"))
    plan = await _plan(db_session, "zebrafish")
    assert "BitmapOr" in plan, plan
    for index in (
        "ix_nodes_name_trgm",
        "ix_nodes_description_trgm",
        "ix_nodes_attributes_text_trgm",
    ):
        assert f"Bitmap Index Scan on {index}" in plan, plan
    assert "Seq Scan" not in plan, plan


async def test_description_and_name_words_use_their_trigram_indexes(
    db_session: AsyncSession,
) -> None:
    """`description ~` and `name ~` are answered from their own trigram index."""
    await db_session.execute(
        text(
            """
            INSERT INTO nodes (id, owner_id, name, description, tags, attributes,
                               favourite, created_at, updated_at, type)
            SELECT gen_random_uuid(), :owner, 'Item ' || n,
                   CASE WHEN n % 5000 = 0 THEN 'zebrafish ' || n
                        ELSE 'filler text ' || n END,
                   '[]'::jsonb, '{}'::jsonb, false,
                   to_timestamp(1700000000 + n), to_timestamp(1700000000 + n),
                   'film'
            FROM generate_series(1, 20000) AS n
            """
        ),
        {"owner": OWNER},
    )
    await db_session.execute(text("ANALYZE nodes"))
    description = await _plan(
        db_session, "", {"kind": "description", "op": "~", "value": "zebrafish"}
    )
    assert "Bitmap Index Scan on ix_nodes_description_trgm" in description, description
    assert "Seq Scan" not in description, description
    name = await _plan(
        db_session, "", {"kind": "name", "op": "~", "value": "Item 19999"}
    )
    assert "Bitmap Index Scan on ix_nodes_name_trgm" in name, name
    assert "Seq Scan" not in name, name


async def test_only_known_characters_unaccent_to_json_escaped_ones(
    db_session: AsyncSession,
) -> None:
    r"""Every character `unaccent` maps to `"`, `\` or a control char is skipped.

    The prefilter skips queries holding such a character; a new one in a future
    Postgres must fail here, listed by code point.
    """
    result = await db_session.execute(
        text(
            r"""
            SELECT i FROM generate_series(1, 1114111) AS i
            WHERE i NOT BETWEEN 55296 AND 57343
              AND immutable_unaccent(chr(i)) ~ '["\\]|[\x01-\x1f]'
            """
        )
    )
    found = {chr(row[0]) for row in result}
    plain = {c for c in found if c in '"\\' or ord(c) < 0x20}
    unexpected = sorted(
        f"U+{ord(c):04X}" for c in found - plain - _UNACCENT_TO_JSON_ESCAPED
    )
    assert not unexpected, unexpected
    stale = sorted(f"U+{ord(c):04X}" for c in _UNACCENT_TO_JSON_ESCAPED - found)
    assert not stale, stale
