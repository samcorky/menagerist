from urllib.parse import urlsplit

import structlog
from starlette.requests import Request  # noqa: TC002

from app.platform import proxy_signals
from app.platform.config import get_api_settings
from app.platform.proxy_signals import ProxySignal
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.log_safe import loggable

logger = structlog.get_logger()

_DEFAULT_PORTS = {"http": 80, "https": 443}


class CrossSiteRequestError(ForbiddenError):
    """Raised when a public sign-in or setup request comes from another site."""

    problem_type = "cross_site_refused"


def _origin_of(scheme: str, netloc: str) -> str:
    """Return `scheme://host[:port]` lower-cased, without a default port."""
    netloc = netloc.lower()
    default = f":{_DEFAULT_PORTS.get(scheme, '')}"
    return f"{scheme}://{netloc.removesuffix(default)}"


async def refuse_cross_site(request: Request) -> None:
    """Refuse a request that a page on another site sent.

    The public sign-in and setup routes have no session, so the CSRF token
    cannot protect them. The browser's own `Sec-Fetch-Site` header decides first
    (page script cannot set it): `cross-site` is refused and `same-origin` passes.
    When it is missing or says `same-site` (older browsers, plain HTTP, a sibling
    subdomain), any `Origin` must be the request's own or a configured CORS
    origin; a wildcard CORS setting does not count. Requests with neither header
    (curl, the CLI, tests) pass.

    A `same-origin` request whose `Origin` differs from the origin the app
    rebuilt from the request is let through but noted: it means a proxy's
    scheme or host is not reaching the app (see `MENAGERIST_TRUSTED_PROXIES`).

    Raises:
        CrossSiteRequestError: If the request is cross-site.
    """
    site = request.headers.get("Sec-Fetch-Site")
    origin = request.headers.get("Origin")
    own = _origin_of(request.url.scheme, request.url.netloc)
    claimed = None
    if origin is not None:
        try:
            parts = urlsplit(origin)
        except ValueError:
            _refuse("malformed origin", site, origin, own)
        claimed = _origin_of(parts.scheme, parts.netloc)

    if site == "cross-site":
        _refuse("browser reports cross-site", site, origin, own)
    if origin is None:
        return
    if site == "same-origin":
        if claimed != own:
            proxy_signals.record(ProxySignal.ORIGIN_MISMATCH)
            logger.warning(
                "same-origin request has a different origin than the app saw",
                claimed_origin=loggable(origin),
                seen_origin=own,
                hint="check MENAGERIST_TRUSTED_PROXIES and the proxy's Host header",
            )
        return
    allowed = {entry for entry in get_api_settings().cors_origins if entry != "*"}
    if claimed != own and claimed not in allowed:
        _refuse("origin differs", site, origin, own)


def _refuse(reason: str, site: str | None, origin: str | None, own: str) -> None:
    logger.warning(
        "cross-site request refused",
        reason=reason,
        sec_fetch_site=loggable(site or ""),
        claimed_origin=loggable(origin or ""),
        seen_origin=own,
    )
    raise CrossSiteRequestError("This request was sent from another site.")
