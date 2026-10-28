import structlog
from starlette.requests import Request  # noqa: TC002

from app.entrypoints.api.shared.http.origin import (
    claimed_origin,
    log_refusal,
    note_origin_mismatch,
    own_origin,
)
from app.platform.config import get_api_settings
from app.shared_kernel.errors import ForbiddenError

logger = structlog.get_logger()


class CrossSiteRequestError(ForbiddenError):
    """Raised when a public sign-in or setup request comes from another site."""

    problem_type = "cross_site_refused"


async def refuse_cross_site(request: Request) -> None:
    """Refuse a request that a page on another site sent.

    The public sign-in and setup routes have no session, so `verify_csrf` does
    not cover them. The browser's own `Sec-Fetch-Site` header decides first
    (page script cannot set it): `cross-site` is refused and `same-origin` passes.
    When it is missing or says `same-site` (older browsers, plain HTTP, a sibling
    subdomain), any `Origin` must be the request's own or a configured CORS
    origin; a wildcard CORS setting does not count. Requests with neither header
    (curl, the CLI, tests) pass.

    A `same-origin` request whose `Origin` differs from the origin the app
    rebuilt from the request is let through but noted: it means a proxy's
    scheme or host is not reaching the app (see `MENAGERIST_API_TRUSTED_PROXIES`).

    Raises:
        CrossSiteRequestError: If the request is cross-site.
    """
    site = request.headers.get("Sec-Fetch-Site")
    origin = request.headers.get("Origin")
    own = own_origin(request)
    claimed = None
    if origin is not None:
        claimed = claimed_origin(origin)
        if claimed is None:
            _refuse("malformed origin", site, origin, own)

    if site == "cross-site":
        _refuse("browser reports cross-site", site, origin, own)
    if origin is None:
        return
    if site == "same-origin":
        note_origin_mismatch(origin, own)
        return
    allowed = {entry for entry in get_api_settings().cors_origins if entry != "*"}
    if claimed != own and claimed not in allowed:
        _refuse("origin differs", site, origin, own)


def _refuse(reason: str, site: str | None, origin: str | None, own: str) -> None:
    log_refusal(reason, site, origin, own)
    raise CrossSiteRequestError("This request was sent from another site.")
