"""Tests for a bundle's source and its items' source keys."""

import pytest

from app.modules.transfer.domain.bundle import Bundle, BundleItem, BundleSource
from app.modules.transfer.domain.errors import InvalidBundleError


def _item(source_key: str | None = None, ref: str = "i") -> BundleItem:
    return BundleItem(ref=ref, name="Alien", source_key=source_key)


def test_a_bundle_needs_no_source() -> None:
    """A bundle needs no source."""
    bundle = Bundle(id="b", items=(_item(),))
    assert bundle.source is None
    assert bundle.items[0].source_key is None


def test_a_bundle_with_a_source_keeps_keys_and_key_field() -> None:
    """A bundle with a source keeps keys and key field."""
    source = BundleSource(name="lddb", key_field="upc")
    bundle = Bundle(id="b", source=source, items=(_item("0123"),))
    assert bundle.source == source
    assert bundle.items[0].source_key == "0123"


def test_a_key_without_a_source_is_refused() -> None:
    """A key without a source is refused."""
    with pytest.raises(InvalidBundleError, match="source"):
        Bundle(id="b", items=(_item("0123"),))


@pytest.mark.parametrize("name", ["", "   "])
def test_a_blank_source_name_is_refused(name: str) -> None:
    """A blank source name is refused."""
    with pytest.raises(InvalidBundleError, match="source needs a name"):
        Bundle(id="b", source=BundleSource(name=name))


@pytest.mark.parametrize("key_field", ["", "  "])
def test_a_blank_key_field_is_refused(key_field: str) -> None:
    """A blank key field is refused."""
    with pytest.raises(InvalidBundleError, match="key field"):
        Bundle(id="b", source=BundleSource(name="lddb", key_field=key_field))


@pytest.mark.parametrize("key", ["", "   "])
def test_a_blank_item_key_is_refused(key: str) -> None:
    """A blank item key is refused."""
    with pytest.raises(InvalidBundleError, match="blank"):
        Bundle(id="b", source=BundleSource(name="lddb"), items=(_item(key),))
