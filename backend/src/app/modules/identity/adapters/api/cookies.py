from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from app.platform.config import IdentitySettings


_SESSION_PREFIX = "__Host-Http-"


def _secure(request: Request, settings: IdentitySettings) -> bool:
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return request.url.scheme == "https"


def session_cookie_name(request: Request, settings: IdentitySettings) -> str:
    """Return `__Host-Http-<name>` when the cookie is Secure, else the plain name.

    The prefix needs `Secure`, `HttpOnly`, `Path=/` and no `Domain`, so the
    browser then refuses a cookie of that name set by a sibling site or by script.
    """
    if _secure(request, settings):
        return _SESSION_PREFIX + settings.cookie_name
    return settings.cookie_name


def session_cookie_value(request: Request, name: str) -> str | None:
    """Return the value of the one cookie named `name`.

    A missing, duplicated or disguised cookie gives None. A disguised cookie has a
    name that only equals `name` once Unicode spaces are trimmed, which Starlette's
    own parser does; a tossed copy must not be read as the real one.
    """
    found: list[str] = []
    for header in request.headers.getlist("cookie"):
        for chunk in header.split(";"):
            key, _, value = chunk.partition("=")
            key = key.strip(" \t")
            if key == name:
                found.append(value.strip(" \t"))
            elif key.strip() == name:
                return None
    return found[0] if len(found) == 1 else None


def set_session_cookies(
    request: Request, response: Response, token: str, settings: IdentitySettings
) -> None:
    """Set the HttpOnly, SameSite=Strict session cookie, prefixed when Secure."""
    response.set_cookie(
        session_cookie_name(request, settings),
        token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        secure=_secure(request, settings),
        httponly=True,
        samesite="strict",
    )


def clear_session_cookies(
    request: Request, response: Response, settings: IdentitySettings
) -> None:
    """Expire the session cookie."""
    response.delete_cookie(
        session_cookie_name(request, settings),
        path="/",
        secure=_secure(request, settings),
        httponly=True,
        samesite="strict",
    )
