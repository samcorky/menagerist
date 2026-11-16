"""Conditional API operations declare the headers they honour, and only those."""

import json
from pathlib import Path
from typing import Any

# The committed API contract; CI keeps it identical to what the app generates.
SPEC = Path(__file__).parents[4] / "openapi.json"

# The status an operation documents when it honours each header.
HEADER_STATUS = {"If-None-Match": "304", "If-Match": "412"}


def _operations() -> list[tuple[str, dict[str, Any]]]:
    paths: dict[str, dict[str, Any]] = json.loads(SPEC.read_text())["paths"]
    return [
        (f"{method.upper()} {path}", operation)
        for path, item in paths.items()
        if path.startswith("/api/v1/")
        for method, operation in item.items()
    ]


def _headers(operation: dict[str, Any]) -> set[str]:
    return {
        parameter["name"]
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "header"
    }


def test_conditional_headers_match_the_documented_statuses() -> None:
    """A 304 comes with If-None-Match, a 412 with If-Match, and never otherwise."""
    mismatched = {
        name: header
        for name, operation in _operations()
        for header, status in HEADER_STATUS.items()
        if (header in _headers(operation)) != (status in operation["responses"])
    }

    assert any("If-Match" in _headers(operation) for _, operation in _operations()), (
        "no operation declares If-Match"
    )
    assert mismatched == {}
