"""Lossless NDJSON encoding shared by reflected snapshots and restores."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON

from app.modules.backup.domain.errors import CorruptBackupError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy import Table


def _json_default(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(f"Unsupported backup value: {type(value).__name__}")


def encode_row(row: Mapping[str, object]) -> bytes:
    """Encode one row, including its terminating newline."""
    return (
        json.dumps(dict(row), default=_json_default, ensure_ascii=False) + "\n"
    ).encode()


def decode_row(row: Mapping[str, object], table: Table) -> dict[str, object]:
    """Restore reflected UUID and timestamp values, rejecting unknown columns."""
    row = dict(row)
    json_nulls = row.pop("$json_nulls", [])
    if not isinstance(json_nulls, list) or any(
        not isinstance(name, str)
        or name not in table.c
        or not isinstance(table.c[name].type, JSON)
        or name not in row
        or row[name] is not None
        for name in json_nulls
    ):
        raise CorruptBackupError("Invalid JSON null metadata.")
    unknown = row.keys() - table.c.keys()
    if unknown:
        raise CorruptBackupError(
            f"Unknown columns in {table.name!r}: {sorted(unknown)}"
        )
    decoded = dict(row)
    for name, value in row.items():
        if value is None:
            if name in json_nulls:
                decoded[name] = JSON.NULL
            continue
        python_type = table.c[name].type.python_type
        if python_type is UUID:
            decoded[name] = UUID(str(value))
        elif python_type is datetime:
            decoded[name] = datetime.fromisoformat(str(value)).astimezone(UTC)
    return decoded
