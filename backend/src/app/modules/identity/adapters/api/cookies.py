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
    """Set the HttpOnly, SameSite=Strict session cookie."""
    response.set_cookie(
        settings.cookie_name,
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
        settings.cookie_name,
        path="/",
        secure=_secure(request, settings),
        httponly=True,
        samesite="strict",
    )
