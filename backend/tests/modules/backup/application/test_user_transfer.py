import hashlib
import json
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_user_database_restorer import (
    InMemoryUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_user_database_snapshot import (
    InMemoryUserDatabaseSnapshot,
)
from app.modules.backup.adapters.persistence.user_transfer_rows import USER_TABLES
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.adapters.storage.in_memory_backup_workspace import (
    InMemoryBackupWorkspace,
)
from app.modules.backup.application.export_user_data import (
    ExportUserData,
    ExportUserDataCommand,
)
from app.modules.backup.application.import_user_data import (
    ImportUserData,
    ImportUserDataCommand,
)
from app.modules.backup.application.restore_backup import archive_manifest
from app.modules.backup.domain.backup import BackupManifest, BackupScope, MediaFileRef
from app.modules.backup.domain.errors import (
    CorruptBackupError,
    ImportCollisionError,
    IncompatibleBackupError,
    RestoreTargetNotEmptyError,
)
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def chunks(data: bytes) -> AsyncIterator[bytes]:
    """Yield an archive chunk."""
    yield data


async def exported(
    *, missing: bool = False
) -> tuple[
    InMemoryBackupStore,
    UUID,
    InMemoryMediaFiles,
    Actor,
    dict[str, list[dict[str, object]]],
]:
    """Build a personal archive alongside another owner's private content."""
    actor, other = Actor(id=uuid7()), Actor(id=uuid7())
    item_id, other_id, asset_id, type_id = uuid7(), uuid7(), uuid7(), uuid7()
    tables: dict[str, list[dict[str, object]]] = {
        "users": [
            {"id": actor.id, "password_hash": "SECRET"},
            {"id": other.id, "password_hash": "FOREIGN"},
        ],
        "sessions": [{"token_hash": "TOKEN"}],
        "nodes": [
            {"id": item_id, "owner_id": actor.id, "name": "Mine", "type": "book"},
            {"id": other_id, "owner_id": other.id, "name": "Private", "type": "secret"},
        ],
        "node_types": [
            {"id": type_id, "slug": "book", "attributes_schema": None},
            {"id": uuid7(), "slug": "secret", "attributes_schema": None},
        ],
        "media_assets": [
            {
                "id": asset_id,
                "owner_id": actor.id,
                "status": "attached",
                "size": 4,
                "sha256": hashlib.sha256(b"data").hexdigest(),
            }
        ],
        "media_attachments": [
            {
                "id": uuid7(),
                "asset_id": asset_id,
                "target_type": "node",
                "target_id": item_id,
            }
        ],
        "collections": [{"id": uuid7(), "owner_id": other.id}],
    }
    media = InMemoryMediaFiles()
    ref = MediaFileRef(
        asset_id=asset_id,
        status="attached",
        size=4,
        sha256=hashlib.sha256(b"data").hexdigest(),
    )
    media.refs[asset_id] = ref
    if not missing:
        media.files[(asset_id, "attached")] = b"data"
    store = InMemoryBackupStore()
    summary = await ExportUserData(
        store,
        InMemoryUserDatabaseSnapshot("rev", tables),
        media,
        OwnerAccessPolicy(),
        app_version="test",
    ).handle(ExportUserDataCommand(), actor)
    return store, summary.id, media, actor, tables


@pytest.mark.parametrize("missing", [False, True])
async def test_two_user_round_trip(missing: bool) -> None:
    """Export never includes another person and import stamps the new owner."""
    store, backup_id, _, source, _ = await exported(missing=missing)
    manifest = await archive_manifest(store, backup_id)
    assert manifest.owner_id == source.id
    assert manifest.scope == BackupScope.USER
    payload = b"".join(store.members[backup_id].values())
    for secret in (b"SECRET", b"FOREIGN", b"TOKEN", b"Private"):
        assert secret not in payload
    assert {table.name for table in manifest.tables} == set(USER_TABLES)
    destination = Actor(id=uuid7())
    restorer, media = InMemoryUserDatabaseRestorer("rev"), InMemoryMediaFiles()
    use_case = ImportUserData(
        store, restorer, media, InMemoryBackupWorkspace(), OwnerAccessPolicy()
    )
    await use_case.handle(ImportUserDataCommand(backup_id=backup_id), destination)
    assert str(restorer.tables["nodes"][0]["owner_id"]) == str(destination.id)
    assert restorer.tables["nodes"][0]["name"] == "Mine"
    assert len(media.files) == (0 if missing else 1)
    with pytest.raises(RestoreTargetNotEmptyError):
        await use_case.handle(ImportUserDataCommand(backup_id=backup_id), destination)


async def test_slug_reuse_and_collision_are_atomic() -> None:
    """Reuse compatible vocabulary and reject collisions without writes."""
    store, backup_id, _, _, tables = await exported()
    existing_type = dict(tables["node_types"][0], id=uuid7())
    existing_owner = uuid7()
    restorer = InMemoryUserDatabaseRestorer(
        "rev",
        {
            "node_types": [existing_type],
            "nodes": [{"id": uuid7(), "owner_id": existing_owner}],
        },
    )
    await ImportUserData(
        store,
        restorer,
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        OwnerAccessPolicy(),
    ).handle(ImportUserDataCommand(backup_id=backup_id), Actor(id=uuid7()))
    assert restorer.tables["node_types"] == [existing_type]
    assert restorer.tables["nodes"][0]["owner_id"] == existing_owner
    for target in (
        {"node_types": [dict(existing_type, attributes_schema={"different": True})]},
        {"nodes": [{"id": tables["nodes"][0]["id"], "owner_id": existing_owner}]},
    ):
        restorer = InMemoryUserDatabaseRestorer("rev", target)
        before = json.dumps(target, default=str)
        with pytest.raises(ImportCollisionError):
            await ImportUserData(
                store,
                restorer,
                InMemoryMediaFiles(),
                InMemoryBackupWorkspace(),
                OwnerAccessPolicy(),
            ).handle(ImportUserDataCommand(backup_id=backup_id), Actor(id=uuid7()))
        assert json.dumps(target, default=str) == before


async def test_wrong_revision_and_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse incompatible archives before mutating the target."""
    store, backup_id, _, _, _ = await exported()
    with pytest.raises(IncompatibleBackupError):
        await ImportUserData(
            store,
            InMemoryUserDatabaseRestorer("other"),
            InMemoryMediaFiles(),
            InMemoryBackupWorkspace(),
            OwnerAccessPolicy(),
        ).handle(ImportUserDataCommand(backup_id=backup_id), Actor(id=uuid7()))
    manifest = await archive_manifest(store, backup_id)

    async def incompatible(*args: object) -> BackupManifest:
        return replace(manifest, scope=BackupScope.INSTANCE)

    monkeypatch.setattr(
        "app.modules.backup.application.import_user_data.archive_manifest", incompatible
    )
    with pytest.raises(IncompatibleBackupError):
        await ImportUserData(
            store,
            InMemoryUserDatabaseRestorer("rev"),
            InMemoryMediaFiles(),
            InMemoryBackupWorkspace(),
            OwnerAccessPolicy(),
        ).handle(ImportUserDataCommand(backup_id=backup_id), Actor(id=uuid7()))


async def test_system_export_remains_personal_and_bad_media_aborts() -> None:
    """System jobs still export one owner and reject damaged originals."""
    store = InMemoryBackupStore()
    snapshot = InMemoryUserDatabaseSnapshot(
        "rev", {"nodes": [{"id": uuid7(), "owner_id": uuid7(), "name": "Private"}]}
    )
    result = await ExportUserData(
        store, snapshot, InMemoryMediaFiles(), OwnerAccessPolicy(), app_version="test"
    ).handle(ExportUserDataCommand(), SYSTEM_ACTOR)
    assert store.members[result.id]["data/nodes.ndjson"] == b""
    media = InMemoryMediaFiles()
    ref = MediaFileRef(asset_id=uuid7(), status="attached", size=1, sha256="0" * 64)
    media.refs[ref.asset_id], media.files[(ref.asset_id, ref.status)] = ref, b"x"
    with pytest.raises(CorruptBackupError):
        await ExportUserData(
            store, snapshot, media, OwnerAccessPolicy(), app_version="test"
        ).handle(ExportUserDataCommand(), SYSTEM_ACTOR)


@pytest.mark.parametrize("data", [b"not-json\n", b"{}\n", b"[]\n", b"{"])
async def test_bad_media_record_rejected(data: bytes) -> None:
    """Malformed asset records fail before any restore mutation."""
    from app.modules.backup.application.import_user_data import _media_records

    with pytest.raises(CorruptBackupError):
        await _media_records(chunks(data))


async def test_duplicate_media_record_rejected() -> None:
    """Repeated assets cannot alias one original to multiple records."""
    from app.modules.backup.application.import_user_data import _media_records

    row = (
        json.dumps(
            {"id": str(uuid7()), "status": "attached", "size": 0, "sha256": "0" * 64}
        ).encode()
        + b"\n"
    )
    with pytest.raises(CorruptBackupError):
        await _media_records(chunks(row + row))


async def test_export_verification_failure_deletes_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An export is never published successfully after verification findings."""
    from app.modules.backup.domain.verification import (
        Finding,
        FindingKind,
        VerificationReport,
    )

    async def invalid(*args: object) -> VerificationReport:
        return VerificationReport(
            findings=[Finding(kind=FindingKind.MISSING, member="missing")]
        )

    monkeypatch.setattr(
        "app.modules.backup.application.export_user_data.verify_archive", invalid
    )
    store = InMemoryBackupStore()
    with pytest.raises(CorruptBackupError):
        await ExportUserData(
            store,
            InMemoryUserDatabaseSnapshot("rev", {}),
            InMemoryMediaFiles(),
            OwnerAccessPolicy(),
            app_version="test",
        ).handle(ExportUserDataCommand(), Actor(id=uuid7()))
    assert await store.list() == []


async def test_expired_exports_are_pruned() -> None:
    """Retention deletes only exports older than the configured boundary."""
    from datetime import UTC, datetime, timedelta

    from app.modules.backup.application.export_user_data import prune_user_exports

    store, backup_id, _, _, _ = await exported()
    now = datetime.now(UTC)
    assert await prune_user_exports(store, older_than=now - timedelta(days=1)) == []
    store.summaries[backup_id] = replace(
        store.summaries[backup_id], created_at=now - timedelta(days=2)
    )
    assert await prune_user_exports(store, older_than=now - timedelta(days=1)) == [
        backup_id
    ]
    assert await store.list() == []


async def test_media_failure_rolls_back_database_and_files() -> None:
    """Failure while writing originals leaves the account and files untouched."""
    store, backup_id, _, _, _ = await exported()

    class FailingMedia(InMemoryMediaFiles):
        async def write(self, ref: MediaFileRef, stream: AsyncIterator[bytes]) -> None:
            await super().write(ref, stream)
            raise RuntimeError("disk full")

    target, media = InMemoryUserDatabaseRestorer("rev"), FailingMedia()
    with pytest.raises(RuntimeError, match="disk full"):
        await ImportUserData(
            store, target, media, InMemoryBackupWorkspace(), OwnerAccessPolicy()
        ).handle(ImportUserDataCommand(backup_id=backup_id), Actor(id=uuid7()))
    assert target.tables == {}
    assert media.files == {}


@pytest.mark.parametrize("field", ["scope", "owner_id", "format", "format_version"])
async def test_incompatible_user_manifest(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every incompatible user archive header fails before import."""
    store, backup_id, _, _, _ = await exported()
    manifest = await archive_manifest(store, backup_id)

    async def incompatible(*args: object) -> BackupManifest:
        if field == "scope":
            return replace(manifest, scope=BackupScope.INSTANCE)
        if field == "owner_id":
            return replace(manifest, owner_id=None)
        if field == "format":
            return replace(manifest, format="unknown")
        return replace(manifest, format_version=2)

    monkeypatch.setattr(
        "app.modules.backup.application.import_user_data.archive_manifest", incompatible
    )
    with pytest.raises(IncompatibleBackupError):
        await ImportUserData(
            store,
            InMemoryUserDatabaseRestorer("rev"),
            InMemoryMediaFiles(),
            InMemoryBackupWorkspace(),
            OwnerAccessPolicy(),
        ).handle(ImportUserDataCommand(backup_id=backup_id), Actor(id=uuid7()))


@pytest.mark.parametrize("late_data", [False, True])
async def test_media_preflight_refuses_unrelated_or_early_originals(
    late_data: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uploaded files cannot target assets outside the imported database rows."""
    from app.modules.backup.adapters.storage.in_memory_backup_reader import (
        InMemoryBackupReader,
    )
    from app.modules.backup.application.import_user_data import _validate_media_records

    store, backup_id, _, _, _ = await exported()
    manifest = await archive_manifest(store, backup_id)
    members = {"media/" + str(manifest.media[0].asset_id): b"data"}
    if late_data:
        members["data/media_assets.ndjson"] = b""

    async def reader(key: UUID) -> InMemoryBackupReader:
        return InMemoryBackupReader(members)

    monkeypatch.setattr(store, "open", reader)
    with pytest.raises(CorruptBackupError):
        await _validate_media_records(store, backup_id, manifest)


@pytest.mark.parametrize("data", [b"xxx\n", b"xxx"])
async def test_media_record_size_is_bounded(
    data: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A compressed archive cannot allocate an unbounded media record."""
    from app.modules.backup.application.import_user_data import _media_records

    monkeypatch.setattr(
        "app.modules.backup.application.import_user_data._MAX_ROW_BYTES", 2
    )
    with pytest.raises(CorruptBackupError, match="size limit"):
        await _media_records(chunks(data))
