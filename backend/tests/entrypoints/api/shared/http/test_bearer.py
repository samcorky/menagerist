"""Reading a bearer token from the `Authorization` header."""

import pytest
from starlette.requests import Request

from app.entrypoints.api.shared.http.bearer import bearer_token


def _request(authorization: str | None) -> Request:
    headers = (
        [] if authorization is None else [(b"authorization", authorization.encode())]
    )
    return Request({"type": "http", "headers": headers})


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer x", "x"),
        ("bearer x", "x"),
        ("BEARER   x  ", "x"),
        ("Bearer ", ""),
        ("Bearer", ""),
        ("Basic abc", None),
        ("Token x", None),
        ("", None),
        (None, None),
    ],
)
def test_bearer_token(header: str | None, expected: str | None) -> None:
    """Only the Bearer scheme is a token credential; an empty value is kept."""
    assert bearer_token(_request(header)) == expected
