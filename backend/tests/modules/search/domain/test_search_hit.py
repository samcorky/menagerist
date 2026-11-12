"""How well a title or description matches a search."""

import pytest

from app.modules.search.domain.search_hit import (
    CONTAINS,
    DESCRIPTION,
    EXACT,
    PREFIX,
    WORD_PREFIX,
    SearchHit,
    SearchKind,
    score,
)


@pytest.mark.parametrize(
    ("title", "query", "expected"),
    [
        ("Film", "film", EXACT),
        ("Filmography", "FILM", PREFIX),
        ("Short film", "film", WORD_PREFIX),
        ("Telefilm", "film", CONTAINS),
        ("Café", "cafe", EXACT),
        ("Nothing", "film", 0),
    ],
)
def test_a_title_is_rated_by_how_it_matches(
    title: str, query: str, expected: int
) -> None:
    """Exact, prefix, word prefix and contains rate in that order."""
    assert score(query, title) == expected


def test_a_description_match_is_weaker_than_any_title_match() -> None:
    """A description never beats a title."""
    assert score("keep", "Backups", "How many to keep") == DESCRIPTION
    assert DESCRIPTION < CONTAINS
    assert score("keep", "Backups", None) == 0


def test_a_blank_query_matches_nothing() -> None:
    """Blank text scores nothing."""
    assert score("   ", "Film", "Film") == 0


def test_rating_a_hit_changes_only_its_score() -> None:
    """Rating copies every other field."""
    hit = SearchHit(
        kind=SearchKind.COLLECTION,
        ref="1",
        title="Films",
        slug="films",
        item_count=3,
        attributes={"a": 1},
    )
    rated = hit.rated(80)
    assert rated.score == 80
    assert rated == SearchHit(
        kind=SearchKind.COLLECTION,
        ref="1",
        title="Films",
        slug="films",
        item_count=3,
        attributes={"a": 1},
        score=80,
    )
