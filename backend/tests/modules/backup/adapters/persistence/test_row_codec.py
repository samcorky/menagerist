import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid7

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.backup.adapters.persistence.row_codec import decode_row, encode_row
from app.modules.backup.domain.errors import CorruptBackupError


def test_reflected_types_round_trip() -> None:
    """UUIDs, UTC times, nested JSON and nulls survive NDJSON."""
    table = Table(
        "rows",
        MetaData(),
        Column("id", Uuid),
        Column("created", DateTime),
        Column("data", JSONB),
        Column("nullable", String),
        Column("count", Integer),
    )
    row = {
        "id": uuid7(),
        "created": datetime(2026, 10, 15, 13, tzinfo=timezone(timedelta(hours=1))),
        "data": {"name": "Café", "nested": [True, None, 3]},
        "nullable": None,
        "count": 2,
    }
    encoded = encode_row(row)
    assert encoded.endswith(b"\n")
    decoded = decode_row(json.loads(encoded), table)
    assert decoded == row
    created = decoded["created"]
    assert isinstance(created, datetime)
    assert created.tzinfo is UTC


def test_unknown_columns_refused() -> None:
    """Restore never inserts fields absent from the target schema."""
    table = Table("rows", MetaData(), Column("id", Uuid))
    with pytest.raises(CorruptBackupError, match="Unknown columns"):
        decode_row({"surprise": "value"}, table)


def test_unsupported_values_are_not_silently_stringified() -> None:
    """Unrecognised values fail instead of losing their original type."""
    with pytest.raises(TypeError, match="Unsupported backup value"):
        encode_row({"value": object()})
