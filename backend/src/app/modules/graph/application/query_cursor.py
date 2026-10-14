"""The opaque paging cursor: the last row's sort values and id, as base64url JSON."""

import base64
import json
import math
import re
import uuid
from typing import Any, NoReturn

from app.modules.graph.domain.query import Cursor, InvalidQueryError

_BAD = "Not a valid cursor."
_TOKEN = re.compile(r"[A-Za-z0-9_-]+")


def _invalid(cause: BaseException | None = None) -> NoReturn:
    raise InvalidQueryError(_BAD, path="cursor") from cause


def _reject_constant(name: str) -> NoReturn:
    """Refuse NaN and Infinity, which json.loads otherwise accepts."""
    raise ValueError(name)


def _is_sort_value(value: object) -> bool:
    """Whether `value` is a finite number, a UTF-8 encodable string or None."""
    if value is None:
        return True
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return True
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def encode_cursor(cursor: Cursor) -> str:
    """Encode `cursor` as an unpadded base64url string."""
    raw = json.dumps(
        {"s": list(cursor.sort_values), "i": str(cursor.id)},
        separators=(",", ":"),
        allow_nan=False,
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _parse(token: str) -> tuple[list[Any], uuid.UUID]:
    """Parse a token into its raw sort values and id, or raise a ValueError."""
    if not _TOKEN.fullmatch(token):
        raise ValueError(token)
    padded = token + "=" * (-len(token) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded), parse_constant=_reject_constant)
    values = data["s"]
    if not isinstance(values, list):
        raise TypeError(values)
    return values, uuid.UUID(data["i"])


def decode_cursor(token: str, *, sort_count: int) -> Cursor:
    """Decode a cursor made for a query with `sort_count` sort keys.

    Raises:
        InvalidQueryError: If the token is malformed or belongs to another sort.
    """
    try:
        values, cursor_id = _parse(token)
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        _invalid(error)
    scalar = all(_is_sort_value(v) for v in values)
    if len(values) != sort_count or not scalar:
        _invalid()
    return Cursor(sort_values=tuple(values), id=cursor_id)
