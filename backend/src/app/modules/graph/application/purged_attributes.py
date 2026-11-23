"""Removing an attribute key from the attributes of an item or connection."""

from typing import Any


def purged_attributes(
    attributes: dict[str, Any], key: str, sub_key: str | None
) -> dict[str, Any]:
    """`attributes` with `key`, or `sub_key` from each row of `key`, removed."""
    if sub_key is None:
        return {k: v for k, v in attributes.items() if k != key}
    # `list_with_attribute(..., sub_key=...)` only returns nodes/edges where `key`
    # is already an array holding a matching dict row, so `rows` is always a list here.
    rows = attributes[key]
    purged_rows = [
        {k: v for k, v in row.items() if k != sub_key} if isinstance(row, dict) else row
        for row in rows
    ]
    return {**attributes, key: purged_rows}
