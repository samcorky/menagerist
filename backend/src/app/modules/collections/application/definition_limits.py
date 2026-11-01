import json
import math
from collections.abc import Mapping
from typing import Any, Final

from app.modules.collections.domain.errors import InvalidDefinitionError

# A valid query nests at most 12 levels: four groups, their child lists, a
# condition, its value list and a money operand.
MAX_DEFINITION_DEPTH: Final = 12
MAX_DEFINITION_BYTES: Final = 32 * 1024


def _check_text(text: str) -> None:
    if "\x00" in text:
        raise InvalidDefinitionError("A definition cannot contain NUL characters.")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidDefinitionError(
            "A definition must be valid Unicode text."
        ) from None


def ensure_definition_within_limits(definition: Mapping[str, Any]) -> None:
    """Refuse a definition that could not be stored or returned safely.

    Runs before the checker, so a hostile body never reaches the parser or the
    database. It bounds nesting, size and text encoding only; the grammar is the
    checker's job.

    Raises:
        InvalidDefinitionError: If it nests deeper than `MAX_DEFINITION_DEPTH`,
            holds a NUL character, text that is not valid UTF-8 or a number that
            is not finite, or is larger than `MAX_DEFINITION_BYTES` as JSON.
    """
    # Iterative, so a deeply nested body cannot exhaust the interpreter stack.
    stack: list[tuple[object, int]] = [(definition, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, str):
            _check_text(node)
        elif isinstance(node, float):
            if not math.isfinite(node):
                raise InvalidDefinitionError(
                    "A definition cannot hold NaN or infinity."
                )
        elif isinstance(node, Mapping | list):
            if depth > MAX_DEFINITION_DEPTH:
                raise InvalidDefinitionError(
                    f"A definition can nest up to {MAX_DEFINITION_DEPTH} levels deep."
                )
            children = (
                [part for pair in node.items() for part in pair]
                if isinstance(node, Mapping)
                else node
            )
            stack.extend((child, depth + 1) for child in children)
    size = len(json.dumps(definition, ensure_ascii=False).encode("utf-8"))
    if size > MAX_DEFINITION_BYTES:
        raise InvalidDefinitionError(
            f"A definition can be up to {MAX_DEFINITION_BYTES // 1024} KiB."
        )
