"""Pure archive metadata codecs, safe member names and integrity comparisons."""

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.modules.backup.domain.backup import (
    BackupManifest,
    BackupSummary,
    MediaFileRef,
    MemberDigest,
    TableDigest,
)
from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.backup.domain.verification import (
    Finding,
    FindingKind,
    VerificationReport,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_SHA256 = re.compile(r"[0-9a-f]{64}")
_TABLE = re.compile(r"data/[a-z][a-z0-9_]*\.ndjson")


def validate_member_name(name: str) -> None:
    """Reject traversal, aliases and paths outside the archive vocabulary."""
    if name in {"manifest.json", "checksums.sha256"} or _TABLE.fullmatch(name):
        return
    if name.startswith("media/"):
        asset_id = name.removeprefix("media/")
        try:
            if str(UUID(asset_id)) == asset_id:
                return
        except ValueError:
            pass
    raise CorruptBackupError(f"Unsafe or unexpected archive member: {name}")


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CorruptBackupError("Backup metadata must be a JSON object.")
    return value


def _load(data: bytes) -> dict[str, object]:
    try:
        value: object = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise CorruptBackupError("Invalid backup metadata JSON.") from exc
    return _object(value)


def _text(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise CorruptBackupError(f"Invalid backup metadata field: {key}")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if type(value) is not int or value < 0:
        raise CorruptBackupError(f"Invalid non-negative integer: {key}")
    return value


def _array(payload: dict[str, object], key: str) -> list[object]:
    value = payload[key]
    if not isinstance(value, list):
        raise CorruptBackupError(f"Invalid backup metadata list: {key}")
    return value


def _digest(payload: dict[str, object]) -> str:
    digest = _text(payload, "sha256")
    if not _SHA256.fullmatch(digest):
        raise CorruptBackupError("Invalid SHA-256 digest in backup metadata.")
    return digest


def _date(payload: dict[str, object]) -> datetime:
    value = datetime.fromisoformat(_text(payload, "created_at"))
    if value.tzinfo is None:
        raise CorruptBackupError("Backup timestamps must include a timezone.")
    return value.astimezone(UTC)


def _optional_text(payload: dict[str, object], key: str) -> str | None:
    return None if payload.get(key) is None else _text(payload, key)


def _table(value: object) -> TableDigest:
    table = _object(value)
    name = _text(table, "name")
    validate_member_name(f"data/{name}.ndjson")
    return TableDigest(name=name, rows=_integer(table, "rows"), sha256=_digest(table))


def _media(value: object) -> MediaFileRef:
    media = _object(value)
    return MediaFileRef(
        asset_id=UUID(_text(media, "asset_id")),
        status=_text(media, "status"),
        size=_integer(media, "size"),
        sha256=_digest(media),
    )


def manifest_bytes(manifest: BackupManifest) -> bytes:
    """Encode the manifest, omitting migration fields on ordinary backups."""
    payload = asdict(manifest)
    for key in ("from_revision", "to_revision", "owner_id"):
        if payload[key] is None:
            del payload[key]
    payload["created_at"] = manifest.created_at.astimezone(UTC).isoformat()
    return json.dumps(payload, default=str, separators=(",", ":")).encode()


def parse_manifest(data: bytes) -> BackupManifest:
    """Decode structural metadata without imposing restore compatibility."""
    payload = _load(data)
    try:
        manifest = BackupManifest(
            format=_text(payload, "format"),
            format_version=_integer(payload, "format_version"),
            scope=_text(payload, "scope"),
            app_version=_text(payload, "app_version"),
            alembic_revision=_text(payload, "alembic_revision"),
            label=_text(payload, "label"),
            created_at=_date(payload),
            created_by=UUID(_text(payload, "created_by")),
            owner_id=(
                UUID(_text(payload, "owner_id"))
                if payload.get("owner_id") is not None
                else None
            ),
            tables=[_table(value) for value in _array(payload, "tables")],
            media=[_media(value) for value in _array(payload, "media")],
            media_missing=[
                UUID(str(value)) for value in _array(payload, "media_missing")
            ],
            from_revision=_optional_text(payload, "from_revision"),
            to_revision=_optional_text(payload, "to_revision"),
        )
    except (KeyError, ValueError) as exc:
        raise CorruptBackupError("Invalid or incomplete backup manifest.") from exc
    names = [table.name for table in manifest.tables]
    assets = [ref.asset_id for ref in manifest.media]
    if len(set(names)) != len(names) or len(set(assets)) != len(assets):
        raise CorruptBackupError("Duplicate entries in backup manifest.")
    if not set(manifest.media_missing) <= set(assets):
        raise CorruptBackupError("Missing media must have a manifest record.")
    return manifest


def summary_bytes(summary: BackupSummary) -> bytes:
    """Encode the archive commit marker."""
    payload = asdict(summary)
    payload["created_at"] = summary.created_at.astimezone(UTC).isoformat()
    return json.dumps(payload, default=str, separators=(",", ":")).encode()


def parse_summary(data: bytes) -> BackupSummary:
    """Decode a summary without opening its archive."""
    payload = _load(data)
    try:
        return BackupSummary(
            id=UUID(_text(payload, "id")),
            label=_text(payload, "label"),
            size=_integer(payload, "size"),
            created_at=_date(payload),
            alembic_revision=_text(payload, "alembic_revision"),
            app_version=_text(payload, "app_version"),
        )
    except (KeyError, ValueError) as exc:
        raise CorruptBackupError("Invalid or incomplete backup summary.") from exc


def checksum_bytes(digests: Mapping[str, MemberDigest]) -> bytes:
    """Encode sha256sum-compatible lines for uncompressed members."""
    return "".join(
        f"{digest.sha256}  {name}\n" for name, digest in digests.items()
    ).encode()


def _checksums(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for line in data.decode().splitlines():
            digest, name = line.split("  ", 1)
            validate_member_name(name)
            if (
                not _SHA256.fullmatch(digest)
                or name in result
                or name == "checksums.sha256"
            ):
                raise ValueError("invalid checksum entry")
            result[name] = digest
        if not result:
            raise ValueError("empty checksums")
    except (ValueError, UnicodeError) as exc:
        raise CorruptBackupError("Invalid checksums.sha256 contents.") from exc
    return result


def _compare(
    findings: list[Finding],
    name: str,
    expected: str,
    actual: str | None,
    kind: FindingKind = FindingKind.CHECKSUM_MISMATCH,
) -> None:
    if expected != actual:
        findings.append(
            Finding(
                kind=FindingKind.MISSING if actual is None else kind,
                member=name,
                expected=expected,
                actual=actual,
            )
        )


def _manifest_findings(
    manifest: BackupManifest,
    actual: Mapping[str, MemberDigest],
    findings: list[Finding],
) -> None:
    expected = {"manifest.json", "checksums.sha256"}
    for table in manifest.tables:
        name = f"data/{table.name}.ndjson"
        expected.add(name)
        member = actual.get(name)
        _compare(
            findings, name, table.sha256, None if member is None else member.sha256
        )
        if member is not None:
            _compare(findings, name, str(table.rows), str(member.lines))
    for media in manifest.media:
        if media.asset_id in manifest.media_missing:
            continue
        name = f"media/{media.asset_id}"
        expected.add(name)
        member = actual.get(name)
        _compare(
            findings,
            name,
            media.sha256,
            None if member is None else member.sha256,
            FindingKind.MEDIA_MISMATCH,
        )
        if member is not None:
            _compare(
                findings,
                name,
                str(media.size),
                str(member.size),
                FindingKind.MEDIA_MISMATCH,
            )
    findings.extend(
        Finding(kind=FindingKind.UNEXPECTED, member=name)
        for name in actual.keys() - expected
    )


def _name_findings(actual: Mapping[str, MemberDigest]) -> list[Finding]:
    findings: list[Finding] = []
    for name in actual:
        try:
            validate_member_name(name)
        except CorruptBackupError:
            findings.append(Finding(kind=FindingKind.UNEXPECTED, member=name))
    return findings


def analyse_members(
    actual: Mapping[str, MemberDigest],
    manifest_data: bytes | None,
    checksum_data: bytes | None,
) -> VerificationReport:
    """Compare every observed member with both integrity indexes."""
    findings = _name_findings(actual)
    if manifest_data is None:
        findings.append(Finding(kind=FindingKind.MISSING, member="manifest.json"))
    else:
        try:
            manifest = parse_manifest(manifest_data)
        except CorruptBackupError as exc:
            findings.append(
                Finding(
                    kind=FindingKind.MANIFEST_INVALID,
                    member="manifest.json",
                    actual=str(exc),
                )
            )
        else:
            _manifest_findings(manifest, actual, findings)
    if checksum_data is None:
        findings.append(Finding(kind=FindingKind.MISSING, member="checksums.sha256"))
    else:
        try:
            checksums = _checksums(checksum_data)
        except CorruptBackupError as exc:
            findings.append(
                Finding(
                    kind=FindingKind.MANIFEST_INVALID,
                    member="checksums.sha256",
                    actual=str(exc),
                )
            )
        else:
            for name, digest in checksums.items():
                member = actual.get(name)
                _compare(
                    findings, name, digest, None if member is None else member.sha256
                )
            findings.extend(
                Finding(
                    kind=FindingKind.MISSING, member="checksums.sha256", expected=name
                )
                for name in actual.keys() - checksums.keys() - {"checksums.sha256"}
            )
    return VerificationReport(findings=findings)
