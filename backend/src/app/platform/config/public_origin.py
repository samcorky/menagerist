"""What other settings fall back to when `api.public_origin` says where the app lives.

Plain functions rather than validators, so each settings group stays an independent
class; an explicit setting always wins over anything derived here.
"""

from urllib.parse import urlsplit

from app.platform.config.api import ApiSettings  # noqa: TC001 - used in signatures


def public_host(api: ApiSettings) -> str | None:
    """Return the public address's host without port or brackets, or `None`."""
    if api.public_origin is None:
        return None
    return urlsplit(api.public_origin).hostname


def public_is_https(api: ApiSettings) -> bool | None:
    """Return whether the public address is HTTPS, or `None` when it is not set."""
    if api.public_origin is None:
        return None
    return urlsplit(api.public_origin).scheme == "https"
