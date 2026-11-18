"""A bundle's item limit can be raised by the source that builds it."""

import pytest

from app.modules.transfer.domain.bundle import MAX_ITEMS, Bundle, BundleItem
from app.modules.transfer.domain.errors import InvalidBundleError


def _items(count: int) -> tuple[BundleItem, ...]:
    return tuple(BundleItem(ref=f"i{n}", name="x") for n in range(count))


def test_the_default_limit_still_refuses_more_than_500_items() -> None:
    """Existing sources keep their limit."""
    with pytest.raises(InvalidBundleError, match="at most 500 items"):
        Bundle(id="b", items=_items(MAX_ITEMS + 1))


def test_a_source_may_raise_the_limit() -> None:
    """A bundle with its own limit accepts that many items."""
    bundle = Bundle(id="b", items=_items(MAX_ITEMS + 1), item_limit=5000)
    assert len(bundle.items) == MAX_ITEMS + 1


def test_a_raised_limit_is_still_a_limit() -> None:
    """Beyond its own limit a bundle is refused, naming that limit."""
    with pytest.raises(InvalidBundleError, match="at most 600 items"):
        Bundle(id="b", items=_items(601), item_limit=600)
