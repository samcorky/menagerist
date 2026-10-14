"""Text folding and matching shared by the in-memory list and search paths."""

import unicodedata
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from app.modules.graph.domain.node import Node


def fold(text: str) -> str:
    """Casefold `text` and strip accents, as Postgres `unaccent` does."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def sort_key(text: str) -> str:
    """Lower-case `text` and strip accents: the order names are sorted in."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def scalar_values(value: Any) -> Iterator[str]:  # noqa: ANN401
    """Yield every string and number inside `value`; never keys, booleans or nulls."""
    if isinstance(value, dict):
        for inner in value.values():
            yield from scalar_values(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from scalar_values(inner)
    elif isinstance(value, str):
        yield value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield str(value)


def text_matches(
    node: Node,
    needle: str,
    exclusions: Mapping[str, Sequence[str]] | None,
) -> bool:
    """Whether `needle` (already folded) is found in the node's searchable text."""
    if needle in fold(node.name) or needle in fold(node.description or ""):
        return True
    skipped = (exclusions or {}).get(node.type, ()) if node.type else ()
    attributes = {k: v for k, v in node.attributes.items() if k not in skipped}
    return any(needle in fold(text) for text in scalar_values(attributes))
