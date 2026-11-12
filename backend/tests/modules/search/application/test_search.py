"""Searching every source and ranking across kinds."""

from uuid import uuid7

import pytest

from app.modules.search.adapters.persistence.in_memory_search_source import (
    InMemorySearchSource,
)
from app.modules.search.application.search import MAX_CANDIDATES, Search, SearchQuery
from app.modules.search.domain.search_hit import ELSEWHERE, SearchHit, SearchKind
from app.shared_kernel.access_guard import DenyAllAccessGuard, InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

MEMBER = Actor(id=uuid7(), roles=frozenset({"member"}))


def hit(kind: SearchKind, title: str, description: str | None = None) -> SearchHit:
    """A candidate of the given kind."""
    return SearchHit(kind=kind, ref=title, title=title, description=description)


def search(*sources: InMemorySearchSource) -> Search:
    """A search over the given sources that lets everyone in."""
    return Search(sources, InMemoryAccessGuard())


async def test_the_best_match_leads_whichever_kind_it_is_in() -> None:
    """A perfect match in a small kind outranks a weak one in a large kind."""
    items = InMemorySearchSource(
        SearchKind.ITEM,
        [hit(SearchKind.ITEM, "Telefilm"), hit(SearchKind.ITEM, "Filmography")],
    )
    types = InMemorySearchSource(
        SearchKind.ITEM_TYPE, [hit(SearchKind.ITEM_TYPE, "Film")]
    )
    outcome = await search(items, types).handle(SearchQuery(q="film"), MEMBER)
    assert [h.title for h in outcome.hits] == ["Film", "Filmography", "Telefilm"]
    assert outcome.hits[0].score > outcome.hits[1].score > outcome.hits[2].score


async def test_ties_fall_back_to_the_kind_order_then_the_title() -> None:
    """Equal scores are ordered by kind, then title."""
    settings = InMemorySearchSource(
        SearchKind.SETTING, [hit(SearchKind.SETTING, "Film b")]
    )
    items = InMemorySearchSource(
        SearchKind.ITEM,
        [hit(SearchKind.ITEM, "Film z"), hit(SearchKind.ITEM, "Film a")],
    )
    outcome = await search(settings, items).handle(SearchQuery(q="film"), MEMBER)
    assert [h.title for h in outcome.hits] == ["Film a", "Film z", "Film b"]


async def test_a_match_on_neither_title_nor_description_still_counts() -> None:
    """A source may match on something the search cannot see."""
    items = InMemorySearchSource(SearchKind.ITEM, [hit(SearchKind.ITEM, "Dune")])
    outcome = await search(items).handle(SearchQuery(q="arrakis"), MEMBER)
    assert [h.score for h in outcome.hits] == [ELSEWHERE]


async def test_each_kind_is_limited_after_ranking_and_asked_for_extra() -> None:
    """Each source over-fetches, then only the best are kept."""
    items = InMemorySearchSource(
        SearchKind.ITEM,
        [hit(SearchKind.ITEM, f"x film {n}") for n in range(8)]
        + [hit(SearchKind.ITEM, "Film")],
    )
    outcome = await search(items).handle(SearchQuery(q="film", limit=2), MEMBER)
    assert outcome.hits[0].title == "Film"
    assert len(outcome.hits) == 2
    assert items.asked == [("film", 10)]


async def test_candidates_asked_for_are_capped() -> None:
    """The over-fetch has a ceiling."""
    items = InMemorySearchSource(SearchKind.ITEM)
    await search(items).handle(SearchQuery(q="film", limit=20), MEMBER)
    assert items.asked == [("film", MAX_CANDIDATES)]


async def test_a_kind_the_actor_may_not_see_is_left_out_silently() -> None:
    """A refusal drops the kind without a failure."""
    settings = InMemorySearchSource(
        SearchKind.SETTING, [hit(SearchKind.SETTING, "Film")], forbidden=True
    )
    items = InMemorySearchSource(SearchKind.ITEM, [hit(SearchKind.ITEM, "Film")])
    outcome = await search(settings, items).handle(SearchQuery(q="film"), MEMBER)
    assert [h.kind for h in outcome.hits] == [SearchKind.ITEM]
    assert outcome.failed == []


async def test_a_broken_source_is_reported_and_the_others_still_answer() -> None:
    """A broken source is named while the rest answer."""
    items = InMemorySearchSource(SearchKind.ITEM, broken=True)
    types = InMemorySearchSource(
        SearchKind.ITEM_TYPE, [hit(SearchKind.ITEM_TYPE, "Film")]
    )
    outcome = await search(items, types).handle(SearchQuery(q="film"), MEMBER)
    assert outcome.failed == [SearchKind.ITEM]
    assert [h.kind for h in outcome.hits] == [SearchKind.ITEM_TYPE]


async def test_someone_who_is_not_signed_in_is_refused_before_any_source_is_asked() -> (
    None
):
    """The guard runs before any source."""
    items = InMemorySearchSource(SearchKind.ITEM)
    with pytest.raises(ForbiddenError):
        await Search([items], DenyAllAccessGuard()).handle(SearchQuery(q="x"), MEMBER)
    assert items.asked == []


async def test_blank_text_finds_nothing_and_asks_no_one() -> None:
    """Blank text is answered without asking a source."""
    items = InMemorySearchSource(SearchKind.ITEM, [hit(SearchKind.ITEM, "Film")])
    outcome = await search(items).handle(SearchQuery(q="   "), MEMBER)
    assert outcome.hits == []
    assert items.asked == []
