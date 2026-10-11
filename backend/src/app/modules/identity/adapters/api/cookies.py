import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from app.platform.config import IdentitySettings


def _secure(request: Request, settings: IdentitySettings) -> bool:
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return request.url.scheme == "https"


def set_session_cookies(
    request: Request, response: Response, token: str, settings: IdentitySettings
) -> None:
    """Set the HttpOnly session cookie and a fresh script-readable CSRF cookie."""
    secure = _secure(request, settings)
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        secrets.token_urlsafe(32),
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )


def clear_session_cookies(
    request: Request, response: Response, settings: IdentitySettings
) -> None:
    """Expire both cookies."""
    secure = _secure(request, settings)
    response.delete_cookie(
        settings.cookie_name, path="/", secure=secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )
