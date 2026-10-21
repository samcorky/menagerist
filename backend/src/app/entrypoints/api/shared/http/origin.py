from urllib.parse import urlsplit

import structlog
from starlette.requests import Request  # noqa: TC002

from app.platform import proxy_signals
from app.platform.proxy_signals import ProxySignal
from app.shared_kernel.log_safe import loggable

logger = structlog.get_logger()

_DEFAULT_PORTS = {"http": 80, "https": 443}


def origin_of(scheme: str, netloc: str) -> str:
    """Return `scheme://host[:port]` lower-cased, without a default port."""
    netloc = netloc.lower()
    default = f":{_DEFAULT_PORTS.get(scheme, '')}"
    return f"{scheme}://{netloc.removesuffix(default)}"


def own_origin(request: Request) -> str:
    """Return the origin the app rebuilt from the request."""
    return origin_of(request.url.scheme, request.url.netloc)


def claimed_origin(origin: str) -> str | None:
    """Normalise an `Origin` header value, or None if it is malformed.

    `null` and other values without a scheme and host give a string that no real
    origin equals.
    """
    try:
        parts = urlsplit(origin)
    except ValueError:
        return None
    return origin_of(parts.scheme, parts.netloc)


def note_origin_mismatch(origin: str | None, own: str) -> None:
    """Record a `same-origin` request whose `Origin` differs from the app's own.

    It means a proxy's scheme or host is not reaching the app (see
    `MENAGERIST_TRUSTED_PROXIES`).
    """
    if origin is None or claimed_origin(origin) == own:
        return
    proxy_signals.record(ProxySignal.ORIGIN_MISMATCH)
    logger.warning(
        "same-origin request has a different origin than the app saw",
        claimed_origin=loggable(origin),
        seen_origin=own,
        hint="check MENAGERIST_TRUSTED_PROXIES and the proxy's Host header",
    )


def log_refusal(reason: str, site: str | None, origin: str | None, own: str) -> None:
    """Log why a request was refused: reasons and origins only, never cookies."""
    logger.warning(
        "cross-site request refused",
        reason=reason,
        sec_fetch_site=loggable(site or ""),
        claimed_origin=loggable(origin or ""),
        seen_origin=own,
    )
