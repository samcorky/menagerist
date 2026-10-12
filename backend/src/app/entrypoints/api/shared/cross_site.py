from urllib.parse import urlsplit

from starlette.requests import Request  # noqa: TC002

from app.platform.config import get_api_settings
from app.shared_kernel.errors import ForbiddenError

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
    cannot protect them. A request passes when the browser says it is not
    cross-site (`Sec-Fetch-Site`) and any `Origin` is the request's own or a
    configured CORS origin. A wildcard CORS setting does not count. Requests
    with neither header (curl, the CLI, tests) pass.

    Raises:
        CrossSiteRequestError: If the request is cross-site.
    """
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise CrossSiteRequestError("This request was sent from another site.")
    origin = request.headers.get("Origin")
    if origin is None:
        return
    parts = urlsplit(origin)
    claimed = _origin_of(parts.scheme, parts.netloc)
    own = _origin_of(request.url.scheme, request.url.netloc)
    allowed = {entry for entry in get_api_settings().cors_origins if entry != "*"}
    if claimed != own and claimed not in allowed:
        raise CrossSiteRequestError("This request was sent from another site.")
