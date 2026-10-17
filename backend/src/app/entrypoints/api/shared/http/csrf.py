import hmac

from starlette.requests import Request  # noqa: TC002

from app.platform.config import get_identity_settings
from app.shared_kernel.errors import ForbiddenError

CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class CsrfError(ForbiddenError):
    """Raised when a state-changing request lacks a matching CSRF token."""

    problem_type = "csrf_failed"


async def verify_csrf(request: Request) -> None:
    """Require the CSRF header to equal the CSRF cookie on unsafe methods.

    Requests without a session cookie pass: there is nothing to forge, and
    authentication rejects them with 401.

    Raises:
        CsrfError: If either is missing or they differ.
    """
    if request.method in _SAFE_METHODS:
        return
    settings = get_identity_settings()
    if settings.cookie_name not in request.cookies:
        # No session to protect: authentication answers 401 (or setup required).
        return
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get(CSRF_HEADER)
    if (
        not cookie
        or not header
        or not hmac.compare_digest(cookie.encode(), header.encode())
    ):
        raise CsrfError("The request could not be verified. Reload the page.")
