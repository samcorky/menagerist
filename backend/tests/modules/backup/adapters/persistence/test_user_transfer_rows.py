import json
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

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
from app.modules.backup.domain.errors import CorruptBackupError, ImportCollisionError
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


async def _export(
    snapshot: InMemoryUserDatabaseSnapshot, owner: UUID
) -> dict[str, bytes]:
    return {
        m.name: b"".join([c async for c in m.chunks])
        async for m in snapshot.export(scope=ContentFilter.of(owner))
    }


async def test_export_includes_every_live_preset_of_the_owner() -> None:
    """Unreferenced presets travel too; other people's and deleted ones do not."""
    owner, other = uuid7(), uuid7()
    mine, unused, gone, theirs = (uuid7() for _ in range(4))
    base = {"kind": "choice_list", "definition": {"options": []}}
    snapshot = InMemoryUserDatabaseSnapshot(
        "rev",
        {
            "presets": [
                dict(base, id=mine, owner_id=owner, label="A", deleted_at=None),
                dict(base, id=unused, owner_id=owner, label="B", deleted_at=None),
                dict(base, id=gone, owner_id=owner, label="C", deleted_at="then"),
                dict(base, id=theirs, owner_id=other, label="D", deleted_at=None),
            ],
            "node_types": [
                {
                    "id": uuid7(),
                    "owner_id": owner,
                    "slug": "book",
                    "attributes_schema": {"x-menagerist": {"list": str(mine)}},
                }
            ],
        },
    )
    members = await _export(snapshot, owner)
    exported = {
        json.loads(x)["id"] for x in members["data/presets.ndjson"].splitlines()
    }
    assert exported == {str(mine), str(unused)}


async def test_import_creates_new_preset_rows_and_never_reuses_another_owners() -> None:
    """A destination list of the same kind and label stays apart from the import."""
    source, destination, incoming, existing = (uuid7() for _ in range(4))
    definition = {"options": [{"value": "a", "label": "A"}]}
    schema = {"properties": {"state": {"x-menagerist": {"list": str(incoming)}}}}
    tables = {
        "presets": [
            {
                "id": incoming,
                "owner_id": source,
                "kind": "choice_list",
                "label": "State",
                "definition": definition,
                "deleted_at": None,
            }
        ],
        "node_types": [
            {
                "id": uuid7(),
                "owner_id": source,
                "slug": "book",
                "attributes_schema": schema,
                "deleted_at": None,
            }
        ],
    }
    other_people = {
        "id": existing,
        "owner_id": uuid7(),
        "kind": "choice_list",
        "label": "State",
        "definition": definition,
        "deleted_at": None,
    }
    restorer = InMemoryUserDatabaseRestorer("rev", {"presets": [other_people]})
    await restorer.import_user(
        InMemoryUserDatabaseSnapshot("rev", tables).export(
            scope=ContentFilter.of(source)
        ),
        new_owner_id=destination,
    )
    rows = {str(row["id"]): row for row in restorer.tables["presets"]}
    assert set(rows) == {str(existing), str(incoming)}
    assert rows[str(incoming)]["owner_id"] == destination
    assert rows[str(incoming)]["definition"] == definition
    assert rows[str(existing)]["owner_id"] != destination
    assert str(incoming) in str(restorer.tables["node_types"][0]["attributes_schema"])


async def test_import_refuses_a_preset_id_held_by_another_owner() -> None:
    """Ids are kept, so a clash is a collision rather than a silent link."""
    source, incoming = uuid7(), uuid7()
    row = {
        "id": incoming,
        "kind": "choice_list",
        "label": "State",
        "definition": {"options": []},
        "deleted_at": None,
    }
    snapshot = InMemoryUserDatabaseSnapshot(
        "rev", {"presets": [dict(row, owner_id=source)]}
    )
    restorer = InMemoryUserDatabaseRestorer(
        "rev", {"presets": [dict(row, owner_id=uuid7())]}
    )
    with pytest.raises(ImportCollisionError):
        await restorer.import_user(
            snapshot.export(scope=ContentFilter.of(source)), new_owner_id=uuid7()
        )


def test_import_stamps_ownership_and_regenerates_derived_fields() -> None:
    """Presets take the importer as owner; thumbnails are regenerated."""
    actor = uuid7()
    preset = prepare_row("presets", {"owner_id": "someone-else"}, actor)
    assert preset == {"owner_id": actor}
    media = prepare_row(
        "media_assets", {"has_thumbnail": True, "thumbnail_sha256": "old"}, actor
    )
    assert media == {
        "has_thumbnail": False,
        "thumbnail_sha256": None,
        "owner_id": actor,
    }


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
