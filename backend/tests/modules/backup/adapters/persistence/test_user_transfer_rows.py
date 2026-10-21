from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.modules.backup.adapters.persistence.in_memory_user_database_restorer import (
    InMemoryUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_user_database_snapshot import (
    InMemoryUserDatabaseSnapshot,
)
from app.modules.backup.adapters.persistence.in_memory_user_import_validator import (
    InMemoryUserImportValidator,
)
from app.modules.backup.adapters.persistence.user_transfer_rows import (
    prepare_row,
    read_rows,
)
from app.modules.backup.domain.errors import CorruptBackupError
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


@pytest.mark.parametrize("data", [b"invalid\n", b"[]\n", b"{}", b"xxx", b"xxx\n"])
async def test_rows_reject_malformed_or_oversized_input(
    data: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bound incomplete and complete rows as well as requiring JSON objects."""
    monkeypatch.setattr(
        "app.modules.backup.adapters.persistence.user_transfer_rows.MAX_ROW_BYTES", 2
    )
    with pytest.raises(CorruptBackupError):
        _ = [row async for row in read_rows(_chunks(data))]


async def test_preset_reuse_remaps_only_structural_references() -> None:
    """A reused list keeps type references valid without rewriting personal values."""
    source, destination, preset, existing, item = (uuid7() for _ in range(5))
    schema = {"properties": {"status": {"x-menagerist": {"list": str(preset)}}}}
    tables = {
        "presets": [
            {
                "id": preset,
                "kind": "choice_list",
                "label": "State",
                "definition": {"options": []},
                "builtin": True,
            }
        ],
        "node_types": [{"id": uuid7(), "slug": "book", "attributes_schema": schema}],
        "nodes": [
            {
                "id": item,
                "type": "book",
                "owner_id": source,
                "extra_schema": schema,
                "attributes": {"literal": str(preset)},
            }
        ],
    }
    restorer = InMemoryUserDatabaseRestorer(
        "rev", {"presets": [dict(tables["presets"][0], id=existing)]}
    )
    snapshot = InMemoryUserDatabaseSnapshot("rev", tables)
    await restorer.import_user(
        snapshot.export(scope=ContentFilter.of(source)), new_owner_id=destination
    )
    assert len(restorer.tables["presets"]) == 1
    assert restorer.tables["presets"][0]["builtin"] is True
    assert str(existing) in str(restorer.tables["node_types"][0]["attributes_schema"])
    assert str(existing) in str(restorer.tables["nodes"][0]["extra_schema"])
    assert restorer.tables["nodes"][0]["attributes"] == {"literal": str(preset)}


def test_import_normalises_derived_and_privileged_fields() -> None:
    """New rows cannot gain builtin privileges and thumbnails are regenerated."""
    actor = uuid7()
    assert prepare_row("presets", {"builtin": True}, actor, {})["builtin"] is False
    media = prepare_row(
        "media_assets", {"has_thumbnail": True, "thumbnail_sha256": "old"}, actor, {}
    )
    assert media == {
        "has_thumbnail": False,
        "thumbnail_sha256": None,
        "owner_id": actor,
    }
    remapped = prepare_row(
        "example_installations",
        {"entities": [{"kind": "preset", "id": "before"}, "literal"]},
        actor,
        {"presets:before": "after"},
    )
    assert remapped["entities"] == [{"kind": "preset", "id": "after"}, "literal"]


async def test_validation_failure_keeps_target_empty() -> None:
    """Domain validation participates in the same atomic import boundary."""
    source = uuid7()
    snapshot = InMemoryUserDatabaseSnapshot(
        "rev", {"nodes": [{"id": uuid7(), "owner_id": source}]}
    )
    validator = InMemoryUserImportValidator(rejected_table="nodes")
    restorer = InMemoryUserDatabaseRestorer("rev", validator=validator)
    with pytest.raises(CorruptBackupError):
        await restorer.import_user(
            snapshot.export(scope=ContentFilter.of(source)), new_owner_id=uuid7()
        )
    assert restorer.tables == {}


async def test_same_identifier_in_different_vocabulary_tables_is_remapped_safely() -> (
    None
):
    """A type-id collision cannot redirect a schema's preset reference."""
    owner, destination, incoming, saved_list, saved_type = (uuid7() for _ in range(5))
    schema = {"properties": {"state": {"x-menagerist": {"list": str(incoming)}}}}
    target_schema = {
        "properties": {"state": {"x-menagerist": {"list": str(saved_list)}}}
    }
    tables = {
        "presets": [
            {
                "id": incoming,
                "kind": "choice_list",
                "label": "State",
                "definition": {"options": []},
            }
        ],
        "node_types": [{"id": incoming, "slug": "book", "attributes_schema": schema}],
        "nodes": [
            {"id": uuid7(), "owner_id": owner, "type": "book", "extra_schema": schema}
        ],
    }
    target = {
        "presets": [dict(tables["presets"][0], id=saved_list)],
        "node_types": [
            dict(
                tables["node_types"][0], id=saved_type, attributes_schema=target_schema
            )
        ],
    }
    restorer = InMemoryUserDatabaseRestorer("rev", target)
    await restorer.import_user(
        InMemoryUserDatabaseSnapshot("rev", tables).export(
            scope=ContentFilter.of(owner)
        ),
        new_owner_id=destination,
    )
    assert str(saved_list) in str(restorer.tables["nodes"][0]["extra_schema"])
    assert str(saved_type) not in str(restorer.tables["nodes"][0]["extra_schema"])
