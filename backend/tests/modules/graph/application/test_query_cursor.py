import base64
import json
import uuid

import pytest

from app.modules.graph.application.query_cursor import decode_cursor, encode_cursor
from app.modules.graph.domain.query import Cursor, InvalidQueryError

_DEPTH = 100_000
_ID = str(uuid.uuid7())


def _token(payload: str) -> str:
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def test_round_trip() -> None:
    """A cursor survives encoding and decoding."""
    cursor = Cursor(sort_values=("alien", 4.5, None), id=uuid.uuid7())
    assert decode_cursor(encode_cursor(cursor), sort_count=3) == cursor


def test_round_trips_floats_and_integers_exactly() -> None:
    """Numeric sort values round-trip without loss."""
    cursor = Cursor(sort_values=(0.1 + 0.2, 1e300, 7), id=uuid.uuid7())
    decoded = decode_cursor(encode_cursor(cursor), sort_count=3)
    assert decoded == cursor
    assert decoded.sort_values[0] == 0.1 + 0.2
    assert type(decoded.sort_values[2]) is int


def test_round_trips_a_large_representable_integer() -> None:
    """Integers beyond 2**53 but within float range still decode."""
    cursor = Cursor(sort_values=(2**70,), id=uuid.uuid7())
    assert decode_cursor(encode_cursor(cursor), sort_count=1) == cursor


def test_round_trip_keeps_a_whole_float_a_float() -> None:
    """1.0 stays a float and 7 stays an int."""
    cursor = Cursor(sort_values=(1.0, 7), id=uuid.uuid7())
    decoded = decode_cursor(encode_cursor(cursor), sort_count=2)
    assert type(decoded.sort_values[0]) is float
    assert type(decoded.sort_values[1]) is int


def test_encoded_token_is_unpadded_url_safe() -> None:
    """Tokens carry no padding or URL-unsafe characters."""
    token = encode_cursor(Cursor(sort_values=("é?>~",), id=uuid.uuid7()))
    assert "=" not in token
    assert "+" not in token
    assert "/" not in token


@pytest.mark.parametrize(
    "token",
    [
        "",
        "!!!",
        "e30",
        "eyJzIjpbMV19",
        "A",
        "e30=",
        "eyJz=IjpbMV19",
        "é",
        "١٢٣٤",
        _token("[]"),
        _token("5"),
        _token('"x"'),
        _token("null"),
        _token("{not json"),
        _token('{"s": "notalist", "i": "' + str(uuid.uuid7()) + '"}'),
        _token('{"s": [true], "i": "' + str(uuid.uuid7()) + '"}'),
        _token('{"s": [[1]], "i": "' + str(uuid.uuid7()) + '"}'),
        _token('{"s": [{"a": 1}], "i": "' + str(uuid.uuid7()) + '"}'),
        _token('{"s": [1]}'),
        _token('{"s": [1], "i": "not-a-uuid"}'),
        _token('{"s": [1], "i": 5}'),
        _token('{"s": [NaN], "i": "' + str(uuid.uuid7()) + '"}'),
        _token('{"s": [Infinity], "i": "' + str(uuid.uuid7()) + '"}'),
        _token('{"s": [-Infinity], "i": "' + str(uuid.uuid7()) + '"}'),
        _token('{"s":' + "[" * _DEPTH + "]" * _DEPTH + ',"i":"' + _ID + '"}'),
        _token("[" * _DEPTH),
        _token('{"x":' + "[" * _DEPTH + "]" * _DEPTH + ',"s":[1],"i":"' + _ID + '"}'),
        _token('{"s":[1' + "0" * 400 + '],"i":"' + _ID + '"}'),
        _token('{"s":[-1' + "0" * 400 + '],"i":"' + _ID + '"}'),
        _token('{"s":[1e999],"i":"' + _ID + '"}'),
        _token('{"s":[-1e999],"i":"' + _ID + '"}'),
        _token('{"s":["\\ud800"],"i":"' + _ID + '"}'),
        base64.urlsafe_b64encode(b"\xff\xfe\xfd\xfc").decode(),
    ],
    ids=lambda token: f"length-{len(token)}-{token[:10]}",
)
def test_rejects_garbage(token: str) -> None:
    """Malformed tokens raise InvalidQueryError on the cursor path."""
    with pytest.raises(InvalidQueryError, match="cursor") as raised:
        decode_cursor(token, sort_count=1)
    assert raised.value.path == "cursor"


def test_rejects_a_cursor_from_a_different_sort() -> None:
    """A cursor for another sort-key count is rejected."""
    token = encode_cursor(Cursor(sort_values=("a",), id=uuid.uuid7()))
    with pytest.raises(InvalidQueryError, match="cursor"):
        decode_cursor(token, sort_count=2)


def test_decodes_a_hand_built_token() -> None:
    """A well-formed hand-built token decodes."""
    cursor_id = uuid.uuid7()
    payload = json.dumps({"s": [None], "i": str(cursor_id)})
    assert decode_cursor(_token(payload), sort_count=1) == Cursor(
        sort_values=(None,), id=cursor_id
    )
