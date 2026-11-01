"""Reading the session cookie from the raw `Cookie` header."""

import pytest
from starlette.requests import Request

from app.modules.identity.adapters.api.cookies import session_cookie_value

NAME = "__Host-Http-menagerist-session"

# What `str.strip()` removes from a latin-1 decoded header, and so what Starlette's
# own cookie parser would silently trim from a cookie name.
DISGUISES = ["\x85", "\xa0", "\x0b", "\x0c", "\x1c", "\x1f"]


def _request(*cookie_headers: str) -> Request:
    """A request whose Cookie headers are exactly these, as latin-1 bytes."""
    headers = [(b"cookie", value.encode("latin-1")) for value in cookie_headers]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_one_cookie_is_read() -> None:
    """The one cookie with the name gives its value."""
    assert session_cookie_value(_request(f"{NAME}=abc"), NAME) == "abc"


def test_other_cookies_around_it_are_ignored() -> None:
    """Unrelated cookies beside the session do not matter."""
    request = _request(f"theme=dark; {NAME}=abc; lang=en")

    assert session_cookie_value(request, NAME) == "abc"


def test_spaces_and_tabs_around_the_name_and_value_are_trimmed() -> None:
    """Only ASCII spaces and tabs are trimmed around the name and value."""
    assert session_cookie_value(_request(f" \t{NAME} = abc\t"), NAME) == "abc"


def test_no_cookie_header_is_none() -> None:
    """No Cookie header is no session."""
    assert session_cookie_value(_request(), NAME) is None


def test_a_different_name_is_none() -> None:
    """Another cookie name is not the session."""
    assert session_cookie_value(_request("menagerist-session=abc"), NAME) is None


def test_a_cookie_without_an_equals_sign_is_not_the_session() -> None:
    """A bare name reads as an empty value, which no session token equals."""
    assert session_cookie_value(_request(NAME), NAME) == ""


def test_a_duplicate_in_one_header_is_none() -> None:
    """Two cookies with the exact name in one header are ambiguous."""
    assert session_cookie_value(_request(f"{NAME}=a; {NAME}=b"), NAME) is None


def test_a_duplicate_across_headers_is_none() -> None:
    """Two cookies with the exact name in separate headers are ambiguous."""
    assert session_cookie_value(_request(f"{NAME}=a", f"{NAME}=b"), NAME) is None


@pytest.mark.parametrize("space", DISGUISES)
def test_a_disguised_name_is_none(space: str) -> None:
    """A name that only matches once spaces are trimmed is not the cookie."""
    assert session_cookie_value(_request(f"{space}{NAME}=abc"), NAME) is None


@pytest.mark.parametrize("space", DISGUISES)
def test_a_disguised_copy_beside_the_real_cookie_is_none(space: str) -> None:
    """A tossed copy must not win, nor let the real cookie through."""
    request = _request(f"{NAME}=real; {space}{NAME}=tossed")

    assert session_cookie_value(request, NAME) is None


def test_a_utf8_space_makes_a_different_name_not_a_disguise() -> None:
    """U+2000 sent as UTF-8 is not trimmed once read as latin-1: just another name."""
    en_quad = chr(0x2000)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", f"{en_quad}{NAME}=x; {NAME}=real".encode())],
        }
    )

    assert session_cookie_value(request, NAME) == "real"
