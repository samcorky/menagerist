import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid7

import pytest
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, Uuid
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


def test_root_json_null_is_explicit_and_sql_null_stays_none() -> None:
    """Optional row metadata preserves the distinction lost by JSON decoding."""
    table = Table("rows", MetaData(), Column("data", JSONB))
    assert decode_row({"data": None}, table) == {"data": None}
    assert decode_row({"data": None, "$json_nulls": ["data"]}, table) == {
        "data": JSON.NULL
    }


@pytest.mark.parametrize("metadata", [None, "data", [3], ["missing"], ["id"], ["data"]])
def test_invalid_json_null_metadata_is_refused(metadata: object) -> None:
    """Metadata cannot override non-JSON columns or replace actual values."""
    table = Table("rows", MetaData(), Column("id", Uuid), Column("data", JSONB))
    with pytest.raises(CorruptBackupError, match="JSON null metadata"):
        decode_row({"id": None, "data": {}, "$json_nulls": metadata}, table)
