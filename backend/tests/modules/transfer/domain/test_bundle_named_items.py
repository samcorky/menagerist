"""Tests for items found by name, connection keys and a bundle's connection limit."""

import pytest

from app.modules.transfer.domain.bundle import (
    MAX_CONNECTIONS,
    Bundle,
    BundleConnection,
    BundleItem,
    BundleSource,
    NameLookup,
)
from app.modules.transfer.domain.errors import InvalidBundleError

SOURCE = BundleSource(name="csv:signature:code")


def _named(**over: object) -> BundleItem:
    fields: dict[str, object] = {
        "ref": "p",
        "name": "Rick Astley",
        "type_ref": "person",
        "lookup": NameLookup.CREATE,
    }
    return BundleItem(**(fields | over))  # type: ignore[arg-type]


def _joins(key: str | None = None) -> BundleConnection:
    return BundleConnection(
        source_ref="a", target_ref="b", type_ref="r", source_key=key
    )


def test_an_item_found_by_name_has_no_source_key() -> None:
    """An item found by name is not a row, so it cannot carry a row's key."""
    with pytest.raises(InvalidBundleError, match="found by name has no source key"):
        Bundle(id="b", source=SOURCE, items=(_named(source_key="A1"),))


def test_an_item_found_by_name_needs_a_type() -> None:
    """A name is looked up within a type, so an untyped one is refused."""
    with pytest.raises(InvalidBundleError, match="found by name needs a type"):
        Bundle(id="b", items=(_named(type_ref=None),))


def test_a_connection_key_without_a_source_is_refused() -> None:
    """A connection key, like an item's, needs a source."""
    with pytest.raises(InvalidBundleError, match="no source"):
        Bundle(id="b", connections=(_joins("k"),))


@pytest.mark.parametrize("key", ["", "  "])
def test_a_blank_connection_key_is_refused(key: str) -> None:
    """A blank connection key is refused."""
    with pytest.raises(InvalidBundleError, match="blank source key"):
        Bundle(id="b", source=SOURCE, connections=(_joins(key),))


def test_the_connection_limit_is_the_bundles() -> None:
    """A bundle may raise or lower its connection limit, like its item limit."""
    with pytest.raises(InvalidBundleError, match="at most 2 connections"):
        Bundle(id="b", connection_limit=2, connections=(_joins(),) * 3)
    many = Bundle(
        id="b",
        connection_limit=MAX_CONNECTIONS + 1,
        connections=(_joins(),) * (MAX_CONNECTIONS + 1),
    )
    assert len(many.connections) == MAX_CONNECTIONS + 1
