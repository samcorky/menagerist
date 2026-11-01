"""The collections and graph modules each hold the capped-count limit."""

from app.modules.collections.application.get_collection import ITEM_COUNT_CAP
from app.modules.graph.application.search_nodes import TOTAL_CAP


def test_smart_collection_count_cap_matches_the_search_cap() -> None:
    """`collections` cannot import `graph`, so the two constants must agree."""
    assert ITEM_COUNT_CAP == TOTAL_CAP
