"""Tests for the SourceLink aggregate."""

import uuid

from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.source_link import SourceLink

OWNER = uuid.UUID(int=0xA1)


def _link(fields: dict[str, str] | None = None) -> SourceLink:
    return SourceLink.create(
        owner_id=OWNER,
        source="lddb",
        kind=EntityKind.ITEM,
        key="0123",
        entity_id=uuid.uuid7(),
        fields=fields or {"name": "h1"},
    )


def test_create_sets_identity_and_one_timestamp() -> None:
    """Create sets identity and one timestamp."""
    entity_id = uuid.uuid7()
    link = SourceLink.create(
        owner_id=OWNER,
        source="lddb",
        kind=EntityKind.ITEM,
        key="0123",
        entity_id=entity_id,
        fields={"name": "h1"},
    )
    assert link.owner_id == OWNER
    assert (link.source, link.kind, link.key) == ("lddb", EntityKind.ITEM, "0123")
    assert link.entity_id == entity_id
    assert link.fields == {"name": "h1"}
    assert link.created_at == link.updated_at == link.imported_at


def test_create_copies_the_fields() -> None:
    """Create copies the fields."""
    fields = {"name": "h1"}
    link = _link(fields)
    fields["name"] = "changed"
    assert link.fields == {"name": "h1"}


def test_changed_fields_reports_differing_and_one_sided_keys() -> None:
    """Changed fields reports differing and one sided keys."""
    link = _link({"a": "1", "b": "2"})
    assert link.changed_fields({"a": "1", "b": "9", "c": "3"}) == {"b", "c"}


def test_changed_fields_is_empty_when_nothing_differs() -> None:
    """Changed fields is empty when nothing differs."""
    link = _link({"a": "1"})
    assert link.changed_fields({"a": "1"}) == frozenset()


def test_record_import_repoints_refreshes_and_touches() -> None:
    """Record import repoints refreshes and touches."""
    link = _link({"a": "1"})
    before = link.imported_at
    new_id = uuid.uuid7()
    link.record_import(new_id, {"a": "2"})
    assert link.entity_id == new_id
    assert link.fields == {"a": "2"}
    assert link.imported_at >= before
    assert link.updated_at >= before
