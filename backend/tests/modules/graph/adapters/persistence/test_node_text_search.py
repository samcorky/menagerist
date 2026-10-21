"""Free text gives the same answers with and without the trigram prefilter."""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import ARRAY, Text, bindparam, select

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.adapters.persistence.search_sql import (
    _UNACCENT_TO_JSON_ESCAPED,
    _prefilter_is_safe,
    has_matching_value,
    like_pattern,
    search_clause,
    unaccent_ilike,
)
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import ResolvedQuery, parse_query
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.graph.ports.node_repository import NodeRepository

OWNER = uuid.UUID(int=211)
TODAY = date(2026, 10, 15)

# Each value is stored under "notes" on an item named after its index.
VALUES: list[Any] = [
    'say "hi" twice',
    'say "hi" there',
    "C:\\dir\\file",
    "back\\slash",
    'C:\\dir\\"quoted"',
    "line one\nline two",
    "tab\tseparated",
    "carriage\rreturn",
    "bell\x07ring",
    "del\x7fchar",
    "Café Crème Brûlée",
    "STRASSE und Straße",
    "naïve Ærø œuvre",
    "日本語のテキスト",
    "emoji 🎉 party",
    "",
    "   ",
    "50% off_day",
    "100%",
    "a_b",
    "ab",
    1.5,
    42,
    1e3,
    -0.25,
    True,
    False,
    None,
    ["alpha", 7, {"deep": "Nested Value"}],
    {"inner": {"list": ['x "y" z', 3.14]}},
    {"alpha": "keyname only matches as key"},
    "slash/and/forward",
    "uni\u00a0nbsp",
    "ﬁne ligature",
]

# Postgres `unaccent` expands these (ae, oe); the Python fold does not. Pre-existing.
EXPANDING_LIGATURES = {"aero", "oeuvre"}
# Python's fold keeps these as they are, so only the old exact clause is the
# baseline for them (Postgres `unaccent` turns them into `"` or `\\`).
QUOTE_LOOKALIKES = _UNACCENT_TO_JSON_ESCAPED

QUERIES = [
    "say \u201chi\u201d",
    "say \uff02hi\uff02",
    "say \u02bahi",
    "say \u201chi",
    "say hi\u201d",
    "say \u201fhi",
    "say \u2033hi",
    "say \u301dhi\u301e",
    "C:\u2216dir",
    "C:\uff3cdir",
    "C:\ufe68dir\ufe68file",
    "\u2216",
    "\uff3c",
    '"hi"',
    'say "hi"',
    '"',
    "\\",
    "back\\slash",
    "\\dir",
    'dir\\"quoted',
    "line one\nline two",
    "\n",
    "\t",
    "tab\tsep",
    "\r",
    "\x07",
    "bell\x07",
    "del\x7f",
    "cafe",
    "CAFÉ",
    "creme brulee",
    "brûlée",
    "strasse",
    "straße",
    "STRASSE",
    "naive",
    "aero",
    "ærø",
    "oeuvre",
    "日本語",
    "テキスト",
    "🎉",
    "50% off",
    "50% off_day",
    "100%",
    "%",
    "_",
    "a_b",
    "a%b",
    "ab",
    "a",
    "1",
    "1.5",
    "1.50",
    "42",
    "1000",
    "-0.25",
    "0.25",
    "3.14",
    "true",
    "false",
    "null",
    "alpha",
    "deep",
    "inner",
    "list",
    "nested value",
    "keyname",
    "Nested",
    "slash/and",
    "/",
    "uni nbsp",
    "fine",
    "ligature",
    "   ",
    "{",
    "[",
    ":",
    ",",
    "ZZZ-no-match",
    "twice",
    "say",
]


def _resolved(q: str, exclusions: dict[str, list[str]] | None = None) -> ResolvedQuery:
    query = parse_query(
        {
            "v": 1,
            "where": {"op": "and", "children": [{"kind": "text", "q": q}]},
        }
    )
    return ResolvedQuery(
        query=query,
        field_kinds=resolve_fields(query, {}).kinds,
        search_exclusions=exclusions or {},
        today=TODAY,
    )


async def _seed(repo: NodeRepository, type_slug: str | None = None) -> None:
    for i, value in enumerate(VALUES):
        await repo.add(
            Node.create(
                owner_id=OWNER,
                name=f"item {i:02d}",
                type=type_slug,
                attributes={"notes": value, "secret": f"hidden-{i:02d}"},
            )
        )


async def _names(
    repo: NodeRepository, q: str, exclusions: dict[str, list[str]] | None = None
) -> list[str]:
    hits = await repo.search(
        scope=ContentFilter.of(OWNER),
        resolved=_resolved(q, exclusions),
        after=None,
        limit=100,
    )
    return sorted(hit.node.name for hit in hits)


@pytest.mark.parametrize(
    ("q", "safe"),
    [
        ("abc", True),
        ("cafe au lait", True),
        ("café", True),
        ("日本語", True),
        ("50% off_day", True),
        ("a/b/c", True),
        ("\x7f del", True),
        ("", False),
        ("a", False),
        ("ab", False),
        ('say "hi"', False),
        ('"', False),
        ("back\\slash", False),
        ("\\", False),
        ("a\nbc", False),
        ("a\tbc", False),
        ("\x00bc", False),
        ("abc\x1f", False),
        ("say \u201chi\u201d", False),
        ("say \uff02hi", False),
        ("C:\u2216dir", False),
        ("C:\uff3cdir", False),
        ("abc\u2033", False),
        ("caf\u00e9 \u00e6", True),
    ],
)
def test_prefilter_is_safe_rules(q: str, safe: bool) -> None:
    """A query is unsafe if JSON escapes it in attribute text or it is too short."""
    assert _prefilter_is_safe(q) is safe


def test_clause_uses_prefilter_only_for_safe_queries() -> None:
    """The prefilter adds one `attributes::text` test, and only for a safe query."""
    safe = str(search_clause("alien", None))
    unsafe = str(search_clause('"alien"', None))
    assert "CAST(nodes.attributes AS TEXT)" in safe
    assert "CAST(nodes.attributes AS TEXT)" not in unsafe


@pytest.mark.integration
@pytest.mark.parametrize("q", QUERIES)
async def test_prefiltered_clause_matches_the_reference_and_the_exact_scan(
    db_session: AsyncSession, q: str
) -> None:
    """The prefiltered clause returns what the in-memory reference and old scan do."""
    memory = InMemoryNodeRepository()
    await _seed(memory)
    postgres = SqlAlchemyNodeRepository(db_session)
    await _seed(postgres)
    pattern = like_pattern(q)
    exact_only = (
        unaccent_ilike(NodeModel.name, pattern)
        | unaccent_ilike(NodeModel.description, pattern)
        | has_matching_value(NodeModel.attributes, pattern)
    )
    rows = await db_session.execute(select(NodeModel.name).where(exact_only))
    old = sorted(row[0] for row in rows)
    assert await _names(postgres, q) == old
    if q not in EXPANDING_LIGATURES and not QUOTE_LOOKALIKES & set(q):
        assert old == await _names(memory, q)


@pytest.mark.integration
@pytest.mark.parametrize("q", QUERIES)
async def test_prefilter_respects_type_exclusions(
    db_session: AsyncSession, q: str
) -> None:
    """Excluded keys stay unsearchable with the prefilter in front."""
    memory = InMemoryNodeRepository()
    await _seed(memory, "film")
    postgres = SqlAlchemyNodeRepository(db_session)
    await _seed(postgres, "film")
    for exclusions in ({"film": ["notes"]}, {"film": ["secret"]}):
        pattern = like_pattern(q)
        rows = await db_session.execute(
            select(NodeModel.name).where(
                unaccent_ilike(NodeModel.name, pattern)
                | has_matching_value(
                    NodeModel.attributes.op("-")(
                        bindparam("keys", exclusions["film"], type_=ARRAY(Text))
                    ),
                    pattern,
                )
            )
        )
        assert await _names(postgres, q, exclusions) == sorted(r[0] for r in rows)
        if q not in EXPANDING_LIGATURES and not QUOTE_LOOKALIKES & set(q):
            assert await _names(postgres, q, exclusions) == await _names(
                memory, q, exclusions
            )


@pytest.mark.integration
async def test_hidden_values_found_only_without_exclusion(
    db_session: AsyncSession,
) -> None:
    """A value under an excluded key is found only when the key is not excluded."""
    postgres = SqlAlchemyNodeRepository(db_session)
    await _seed(postgres, "film")
    assert await _names(postgres, "hidden-03") == ["item 03"]
    assert await _names(postgres, "hidden-03", {"film": ["secret"]}) == []
