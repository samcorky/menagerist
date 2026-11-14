from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from app.platform.config import IdentitySettings


_SESSION_PREFIX = "__Host-Http-"

_COOKIE_NOTE = (
    "The name is the configured session cookie name (`menagerist-session` by"
    + " default), prefixed `__Host-Http-` when the cookie is Secure. The cookie is"
    + " `HttpOnly`, `SameSite=Strict` and `Path=/`, has no `Domain`, and is `Secure`"
    + " over HTTPS or when `cookie_secure` is `always`."
)

_DEVICE_NOTE = (
    " A second cookie, named by `device_cookie_name` (`menagerist-device` by"
    + " default) with the same prefix and attributes, remembers the browser for"
    + " `device_ttl_days`; it is kept on sign-out."
)


def session_cookie_header(*, clears: bool = False) -> dict[str, Any]:
    """Return the OpenAPI `Set-Cookie` header entry for a session cookie response.

    Declared beside the route, so the docs follow the routes that call
    `set_session_cookies` or `clear_session_cookies`.
    """
    if clears:
        description = (
            "Clears the session cookie with `Max-Age=0` when a session was ended."
            + " The device cookie is left alone. "
            + _COOKIE_NOTE
        )
        example = "menagerist-session=; Max-Age=0; Path=/; HttpOnly; SameSite=strict"
    else:
        description = (
            "Sets the session cookie. Its value is an opaque token, not to be"
            + " parsed, and it lasts for the configured session lifetime"
            + " (`Max-Age`). "
            + _COOKIE_NOTE
            + _DEVICE_NOTE
        )
        example = (
            "menagerist-session=<opaque-token>; Max-Age=2592000; Path=/; HttpOnly;"
            + " SameSite=strict"
        )
    return {
        "Set-Cookie": {
            "description": description,
            "schema": {"type": "string", "examples": [example]},
        }
    }


def _secure(request: Request, settings: IdentitySettings) -> bool:
    if settings.cookie_secure in ("always", "never"):
        return settings.cookie_secure == "always"
    return request.url.scheme == "https"


def _cookie_name(request: Request, settings: IdentitySettings, name: str) -> str:
    """Return `__Host-Http-<name>` when cookies are Secure, else the plain name.

    The prefix needs `Secure`, `HttpOnly`, `Path=/` and no `Domain`, so the
    browser then refuses a cookie of that name set by a sibling site or by script.
    """
    if _secure(request, settings):
        return _SESSION_PREFIX + name
    return name


def session_cookie_name(request: Request, settings: IdentitySettings) -> str:
    """Return the session cookie's name, prefixed when Secure."""
    return _cookie_name(request, settings, settings.cookie_name)


def device_cookie_name(request: Request, settings: IdentitySettings) -> str:
    """Return the device cookie's name, prefixed when Secure."""
    return _cookie_name(request, settings, settings.device_cookie_name)


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
    request: Request,
    response: Response,
    token: str,
    settings: IdentitySettings,
    *,
    device_token: str,
) -> None:
    """Set the session and device cookies, HttpOnly and SameSite=Strict."""
    secure = _secure(request, settings)
    response.set_cookie(
        session_cookie_name(request, settings),
        token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        device_cookie_name(request, settings),
        device_token,
        max_age=settings.device_ttl_days * 86400,
        path="/",
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookies(
    request: Request, response: Response, settings: IdentitySettings
) -> None:
    """Expire the session cookie; the device cookie stays, as the browser is kept."""
    response.delete_cookie(
        session_cookie_name(request, settings),
        path="/",
        secure=_secure(request, settings),
        httponly=True,
        samesite="strict",
    )
