"""PATCH bodies are declared as RFC 7396 merge patches."""

import json
from pathlib import Path
from typing import Any

from app.entrypoints.api.openapi import _declare_merge_patch

# The committed API contract; CI keeps it identical to what the app generates.
SPEC = Path(__file__).parents[4] / "openapi.json"

MERGE_PATCH = "application/merge-patch+json"


def test_declare_merge_patch_rewrites_only_patch_json_bodies() -> None:
    """Other methods keep their media type; the schema itself is untouched."""
    schema = {"$ref": "#/components/schemas/Thing"}
    spec: dict[str, Any] = {
        "paths": {
            "/things/{id}": {
                "patch": {
                    "requestBody": {"content": {"application/json": {"schema": schema}}}
                },
                "put": {
                    "requestBody": {"content": {"application/json": {"schema": schema}}}
                },
            },
            "/things/{id}/read": {"get": {}},
        }
    }

    _declare_merge_patch(spec)

    patch = spec["paths"]["/things/{id}"]["patch"]["requestBody"]["content"]
    put = spec["paths"]["/things/{id}"]["put"]["requestBody"]["content"]
    assert patch == {MERGE_PATCH: {"schema": schema}}
    assert list(put) == ["application/json"]


def test_every_patch_body_is_a_merge_patch() -> None:
    """A new PATCH route must not slip through as plain application/json."""
    paths = json.loads(SPEC.read_text())["paths"]
    media_types = {
        path: sorted(operations["patch"]["requestBody"]["content"])
        for path, operations in paths.items()
        if "patch" in operations
    }

    assert media_types
    assert {
        path: types for path, types in media_types.items() if types != [MERGE_PATCH]
    } == {}
