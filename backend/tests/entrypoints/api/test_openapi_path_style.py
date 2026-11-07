"""API path segments are single words; hyphenated ones are listed deliberately."""

import json
import re
from pathlib import Path

# The committed API contract; CI keeps it identical to what the app generates.
SPEC = Path(__file__).parents[4] / "openapi.json"

# Segments that are allowed to contain a hyphen. Add to this only on purpose.
HYPHENATED_SEGMENTS = frozenset({"node-types", "edge-types"})


def _hyphenated_segments() -> dict[str, set[str]]:
    """Map each path to the hyphenated literal segments it contains."""
    found: dict[str, set[str]] = {}
    for path in json.loads(SPEC.read_text())["paths"]:
        literals = re.sub(r"\{[^}]*\}", "", path).split("/")
        hyphenated = {segment for segment in literals if "-" in segment}
        if hyphenated:
            found[path] = hyphenated
    return found


def test_hyphenated_path_segments_are_explicitly_allowed() -> None:
    """A new hyphenated segment fails until it is added to the allow list."""
    unexpected = {
        path: sorted(segments - HYPHENATED_SEGMENTS)
        for path, segments in _hyphenated_segments().items()
        if segments - HYPHENATED_SEGMENTS
    }
    assert unexpected == {}


def test_allow_list_has_no_stale_entries() -> None:
    """Remove an allowed segment once no route uses it."""
    used = {s for segments in _hyphenated_segments().values() for s in segments}
    assert HYPHENATED_SEGMENTS - used == set()
