import uuid
from typing import Any

import pytest

from app.modules.graph.application.choice_lists import (
    check_list_refs,
    resolve_choice_lists,
    strip_list_enums,
)
from app.modules.graph.domain.errors import InvalidSchemaError

LIST_ID = str(uuid.UUID("6f1d2a7e-3c4b-4e5f-8a9b-0c1d2e3f4a5b"))


class FakeSource:
    """Stands in for the presets-backed choice list source."""

    def __init__(self, lists: dict[str, list[str]]) -> None:
        self._lists = lists

    async def options(self, list_id: str) -> list[str] | None:
        """Return the options for `list_id`, if known."""
        return self._lists.get(list_id)


def _linked(
    list_id: str = LIST_ID, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return a schema with one linked choice field and one plain text field."""
    return {
        "type": "object",
        "properties": {
            "condition": {
                "type": "string",
                "enum": ["stale"],
                "x-menagerist": {"kind": "choice", "list": list_id},
                **(extra or {}),
            },
            "title": {"type": "string"},
        },
    }


def test_strip_removes_enum_only_from_linked_fields() -> None:
    """Stripping removes `enum` from linked fields and keeps the reference."""
    stripped = strip_list_enums(_linked())
    assert "enum" not in stripped["properties"]["condition"]
    assert stripped["properties"]["condition"]["x-menagerist"]["list"] == LIST_ID


def test_strip_returns_schema_unchanged_without_links() -> None:
    """A schema with no linked fields is returned as it is."""
    schema = {"type": "object", "properties": {"title": {"type": "string"}}}
    assert strip_list_enums(schema) is schema


async def test_check_accepts_a_live_list() -> None:
    """A reference to a live list passes."""
    await check_list_refs(_linked(), FakeSource({LIST_ID: ["Mint"]}))


async def test_check_rejects_a_malformed_id() -> None:
    """A reference that is not a UUID is refused."""
    with pytest.raises(InvalidSchemaError, match="invalid choice list"):
        await check_list_refs(_linked("not-a-uuid"), FakeSource({}))


async def test_check_rejects_an_unknown_list() -> None:
    """A reference to a missing list is refused on write."""
    with pytest.raises(InvalidSchemaError, match="does not exist"):
        await check_list_refs(_linked(), FakeSource({}))


async def test_check_rejects_a_reference_when_no_source_is_wired() -> None:
    """Writes with no list source cannot check references, so they are refused."""
    with pytest.raises(InvalidSchemaError, match="cannot be checked"):
        await check_list_refs(_linked(), None)


async def test_resolve_fills_in_options_from_the_list() -> None:
    """Resolving copies the list's options into `enum`."""
    resolved = await resolve_choice_lists(
        _linked(), FakeSource({LIST_ID: ["Mint", "Good"]})
    )
    assert resolved is not None
    assert resolved["properties"]["condition"]["enum"] == ["Mint", "Good"]
    assert resolved["properties"]["title"] == {"type": "string"}


async def test_resolve_leaves_a_missing_list_unconstrained() -> None:
    """A missing list drops the constraint instead of blocking saves."""
    resolved = await resolve_choice_lists(_linked(), FakeSource({}))
    assert resolved is not None
    assert "enum" not in resolved["properties"]["condition"]


async def test_resolve_passes_through_when_there_is_nothing_to_do() -> None:
    """Schemas with nothing to resolve come back as they are."""
    schema = {"type": "object", "properties": {"title": {"type": "string"}}}
    assert await resolve_choice_lists(schema, FakeSource({})) is schema
    assert await resolve_choice_lists(_linked(), None) is not None


async def test_resolve_ignores_a_schema_without_a_properties_object() -> None:
    """A schema whose `properties` is not an object has nothing to resolve."""
    schema = {"type": "object", "properties": []}
    assert await resolve_choice_lists(schema, FakeSource({})) is schema
