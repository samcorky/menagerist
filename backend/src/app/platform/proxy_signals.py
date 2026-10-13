import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import structlog

logger = structlog.get_logger()


class ProxySignal(StrEnum):
    """Something seen on a request that points at the reverse-proxy setup."""

    # Forwarding headers from a peer outside `MENAGERIST_TRUSTED_PROXIES`.
    UNTRUSTED_FORWARDING = "untrusted_forwarding"
    # A browser said same-origin, but its Origin is not the origin the app saw.
    ORIGIN_MISMATCH = "origin_mismatch"


HINTS = {
    ProxySignal.UNTRUSTED_FORWARDING: (
        "Requests carry forwarding headers from a peer that is not trusted, so"
        + " every visitor looks like the proxy. Set MENAGERIST_TRUSTED_PROXIES to"
        + " the proxy's address or network."
    ),
    ProxySignal.ORIGIN_MISMATCH: (
        "A browser's origin differs from the one the app saw, so the proxy's"
        + " scheme or host is not reaching it. Check MENAGERIST_TRUSTED_PROXIES"
        + " and that the proxy passes Host and X-Forwarded-Proto."
    ),
}

WINDOW = timedelta(hours=1)
_MAX_KEPT = 1000

_lock = threading.Lock()
_seen: dict[ProxySignal, deque[datetime]] = {
    s: deque(maxlen=_MAX_KEPT) for s in ProxySignal
}


def record(signal: ProxySignal, *, now: datetime | None = None) -> None:
    """Note that `signal` was seen. Only a time is kept: no address or header.

    The first sighting in each window is logged as a warning with the fix, so
    the log shows it without a repeat on every request.
    """
    moment = now or datetime.now(UTC)
    with _lock:
        times = _seen[signal]
        first = not times or times[-1] < moment - WINDOW
        times.append(moment)
    if first:
        logger.warning(
            "reverse proxy may be misconfigured",
            signal=signal.value,
            hint=HINTS[signal],
        )


def counts(*, now: datetime | None = None) -> dict[ProxySignal, int]:
    """Return how often each signal was seen within the last `WINDOW` (capped)."""
    cutoff = (now or datetime.now(UTC)) - WINDOW
    with _lock:
        return {s: sum(1 for t in times if t >= cutoff) for s, times in _seen.items()}


def reset() -> None:
    """Forget everything seen. For tests."""
    with _lock:
        for times in _seen.values():
            times.clear()
