from starlette.requests import Request  # noqa: TC002

from app.entrypoints.api.shared.http.origin import (
    claimed_origin,
    log_refusal,
    note_origin_mismatch,
    own_origin,
)
from app.platform.config import get_identity_settings
from app.shared_kernel.errors import ForbiddenError

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CsrfError(ForbiddenError):
    """Raised when a cookie-authenticated unsafe request is not from this site."""

    problem_type = "csrf_failed"


async def verify_csrf(request: Request) -> None:
    """Refuse an unsafe, cookie-authenticated request not sent by this app's own pages.

    The browser's `Sec-Fetch-Site` header decides first (page script cannot set
    it): `same-origin` passes and `cross-site` is refused. Otherwise `Origin`
    must equal the app's own origin; a missing, `null` or malformed value is
    refused. Safe methods and requests without a session cookie pass: there is
    nothing to forge, and authentication answers 401.

    Raises:
        CsrfError: If the request is cross-site, `Origin` is not the app's own
            origin, or neither header is present.
    """
    if request.method in _SAFE_METHODS:
        return
    if not request.cookies.get(get_identity_settings().cookie_name):
        return
    site = request.headers.get("Sec-Fetch-Site")
    origin = request.headers.get("Origin")
    own = own_origin(request)
    if site == "same-origin":
        note_origin_mismatch(origin, own)
        return
    if site == "cross-site":
        reason = "browser reports cross-site"
    elif origin is None:
        reason = "no Sec-Fetch-Site or Origin"
    elif claimed_origin(origin) != own:
        reason = "origin differs"
    else:
        return
    log_refusal(reason, site, origin, own)
    raise CsrfError("This request was not sent from this site's own pages.")
