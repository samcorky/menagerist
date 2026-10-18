import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid7

import pytest

from app.modules.backup.application.archive import (
    analyse_members,
    checksum_bytes,
    manifest_bytes,
    parse_manifest,
    parse_summary,
    summary_bytes,
    validate_member_name,
)
from app.modules.backup.domain.backup import (
    BackupManifest,
    BackupScope,
    BackupSummary,
    MediaFileRef,
    MemberDigest,
    TableDigest,
)
from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.backup.domain.verification import FindingKind


def _digest(data: bytes) -> MemberDigest:
    return MemberDigest(
        size=len(data), sha256=hashlib.sha256(data).hexdigest(), lines=data.count(b"\n")
    )


def _manifest() -> BackupManifest:
    return BackupManifest(
        app_version="1.0",
        alembic_revision="revision",
        label="manual",
        created_at=datetime.now(UTC),
        created_by=uuid7(),
        tables=[TableDigest(name="users", rows=1, sha256=_digest(b"{}\n").sha256)],
    )


def test_manifest_round_trip() -> None:
    """The archive codec preserves typed metadata and omits absent migration fields."""
    original = _manifest()
    assert parse_manifest(manifest_bytes(original)) == original
    assert b"from_revision" not in manifest_bytes(original)
    ref = MediaFileRef(
        asset_id=uuid7(), status="attached", size=3, sha256=_digest(b"abc").sha256
    )
    rich = replace(
        original,
        media=[ref],
        media_missing=[ref.asset_id],
        from_revision="old",
        to_revision="head",
    )
    assert parse_manifest(manifest_bytes(rich)) == rich
    future = replace(original, format="pg_dump", format_version=2, scope="future")
    assert parse_manifest(manifest_bytes(future)) == future
    assert parse_manifest(manifest_bytes(original)).scope == BackupScope.INSTANCE


def test_summary_round_trip() -> None:
    """A summary can be read without touching the archive."""
    summary = BackupSummary(
        id=uuid7(),
        label="manual",
        size=123,
        created_at=datetime.now(UTC),
        alembic_revision="revision",
        app_version="1.0",
    )
    assert parse_summary(summary_bytes(summary)) == summary


@pytest.mark.parametrize(
    "name",
    [
        "manifest.json",
        "checksums.sha256",
        "data/users.ndjson",
        "media/00000000-0000-0000-0000-000000000000",
    ],
)
def test_safe_names(name: str) -> None:
    """Only flat table exports, UUID originals and integrity metadata are allowed."""
    validate_member_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "/manifest.json",
        "../manifest.json",
        "data/../users.ndjson",
        "data/users/extra.ndjson",
        "data/users.json",
        "media/no-id",
        "media/00000000-0000-0000-0000-00000000000A",
        "data\\users.ndjson",
        "",
        "other",
    ],
)
def test_unsafe_names(name: str) -> None:
    """Traversal, ambiguous names and unexpected archive paths are rejected."""
    with pytest.raises(CorruptBackupError):
        validate_member_name(name)


@pytest.mark.parametrize("data", [b"{", b"[]", b"null", b"\xff", b"{}"])
def test_malformed_manifest_and_summary(data: bytes) -> None:
    """Invalid JSON and missing metadata never escape as parser exceptions."""
    for parse in (parse_manifest, parse_summary):
        with pytest.raises(CorruptBackupError):
            parse(data)


def test_member_checksums_and_manifest_agree() -> None:
    """Both integrity indexes describe the actual uncompressed bytes."""
    manifest = _manifest()
    encoded = manifest_bytes(manifest)
    actual = {"data/users.ndjson": _digest(b"{}\n"), "manifest.json": _digest(encoded)}
    checksums = checksum_bytes(actual)
    actual["checksums.sha256"] = _digest(checksums)
    assert analyse_members(actual, encoded, checksums).findings == []
    actual["data/users.ndjson"] = _digest(b"tampered\n")
    report = analyse_members(actual, encoded, checksums)
    assert any(
        f.kind == FindingKind.CHECKSUM_MISMATCH and f.member == "data/users.ndjson"
        for f in report.findings
    )


def test_missing_unexpected_and_invalid_integrity_metadata() -> None:
    """Verification reports structural problems instead of raising them."""
    assert {f.member for f in analyse_members({}, None, None).findings} == {
        "manifest.json",
        "checksums.sha256",
    }
    report = analyse_members({"surprise": _digest(b"x")}, b"{}", b"bad")
    assert {f.kind for f in report.findings} >= {
        FindingKind.MANIFEST_INVALID,
        FindingKind.UNEXPECTED,
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("format_version", True),
        ("created_at", "2026-10-18T12:00:00"),
        ("created_by", "invalid"),
        ("label", 1),
        ("tables", {}),
        ("media", {}),
        ("media_missing", {}),
        ("from_revision", 1),
    ],
)
def test_invalid_manifest_fields(key: str, value: object) -> None:
    """Manifest fields have strict transport types."""
    payload = json.loads(manifest_bytes(_manifest()))
    payload[key] = value
    with pytest.raises(CorruptBackupError):
        parse_manifest(json.dumps(payload).encode())


@pytest.mark.parametrize(
    ("tables", "media", "missing"),
    [
        ([{"name": "users", "rows": 0, "sha256": "bad"}], [], []),
        ([{"name": "users", "rows": 0, "sha256": "0" * 64}] * 2, [], []),
        (
            [],
            [
                {
                    "asset_id": "00000000-0000-0000-0000-000000000000",
                    "status": "attached",
                    "size": 1,
                    "sha256": "0" * 64,
                }
            ]
            * 2,
            [],
        ),
        ([], [], ["00000000-0000-0000-0000-000000000000"]),
    ],
)
def test_manifest_digest_duplicates_and_missing_records(
    tables: list[dict[str, object]], media: list[dict[str, object]], missing: list[str]
) -> None:
    """Malformed indexes cannot hide duplicate or unrecorded content."""
    payload = json.loads(manifest_bytes(_manifest()))
    payload.update(tables=tables, media=media, media_missing=missing)
    with pytest.raises(CorruptBackupError):
        parse_manifest(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "checksums",
    [
        b"",
        b"\xff",
        b"z" * 64 + b"  manifest.json\n",
        b"0" * 64 + b"  checksums.sha256\n",
        (b"0" * 64 + b"  manifest.json\n") * 2,
        b"0" * 64 + b"  ../unsafe\n",
    ],
)
def test_invalid_checksum_indexes(checksums: bytes) -> None:
    """Checksum indexes reject duplicate, unsafe and self-referential entries."""
    report = analyse_members({}, manifest_bytes(_manifest()), checksums)
    assert any(
        f.kind == FindingKind.MANIFEST_INVALID and f.member == "checksums.sha256"
        for f in report.findings
    )


def test_missing_media_and_tables_and_unexpected_members() -> None:
    """Both indexes flag missing data and unmatched member names."""
    ref = MediaFileRef(
        asset_id=uuid7(), status="attached", size=3, sha256=_digest(b"abc").sha256
    )
    manifest = replace(_manifest(), media=[ref])
    encoded = manifest_bytes(manifest)
    actual = {"manifest.json": _digest(encoded), "data/extra.ndjson": _digest(b"x\n")}
    checksums = checksum_bytes(
        {"manifest.json": _digest(encoded), "data/users.ndjson": _digest(b"{}\n")}
    )
    report = analyse_members(actual, encoded, checksums)
    assert {f.member for f in report.findings if f.kind == FindingKind.MISSING} >= {
        "data/users.ndjson",
        f"media/{ref.asset_id}",
        "checksums.sha256",
    }
    assert any(
        f.member == "data/extra.ndjson" and f.kind == FindingKind.UNEXPECTED
        for f in report.findings
    )


def test_wrong_media_size_and_row_count() -> None:
    """Hashes alone cannot mask wrong sizes or recorded table row counts."""
    ref = MediaFileRef(
        asset_id=uuid7(), status="attached", size=4, sha256=_digest(b"abc").sha256
    )
    original = _manifest()
    manifest = replace(
        original, tables=[replace(original.tables[0], rows=2)], media=[ref]
    )
    encoded = manifest_bytes(manifest)
    actual = {
        "data/users.ndjson": _digest(b"{}\n"),
        f"media/{ref.asset_id}": _digest(b"abc"),
        "manifest.json": _digest(encoded),
    }
    report = analyse_members(actual, encoded, checksum_bytes(actual))
    assert {f.kind for f in report.findings} >= {
        FindingKind.MEDIA_MISMATCH,
        FindingKind.CHECKSUM_MISMATCH,
    }


def test_empty_manifest_tables_are_valid() -> None:
    """An archive without media still verifies without special I/O paths."""
    encoded = manifest_bytes(replace(_manifest(), tables=[]))
    actual = {"manifest.json": _digest(encoded)}
    assert analyse_members(actual, encoded, checksum_bytes(actual)).findings == []
