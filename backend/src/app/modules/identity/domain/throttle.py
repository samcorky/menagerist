from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class ThrottleKind(StrEnum):
    """What a failure counter is keyed on."""

    USERNAME = "username"
    USER_ID = "user_id"
    IP = "ip"


@dataclass(kw_only=True, frozen=True)
class ThrottleKey:
    """A failure counter's identity: a kind and a hash of the keyed value."""

    kind: ThrottleKind
    digest: str


@dataclass(kw_only=True, frozen=True)
class ThrottlePolicy:
    """How many failures a key may make in one fixed window before it locks."""

    username_limit: int = 5
    ip_limit: int = 20
    window: timedelta = timedelta(minutes=15)


@dataclass(kw_only=True, frozen=True)
class AttemptWindow:
    """Failures counted in the window that began at `window_start`."""

    count: int
    window_start: datetime
    locked_until: datetime | None = None


def after_failure(
    current: AttemptWindow | None, *, now: datetime, limit: int, window: timedelta
) -> AttemptWindow:
    """Return the counter after one more failure at `now`.

    A fixed window: the failure that reaches `limit` locks until the window
    ends, and a failure after the window has ended starts a new one.
    """
    if current is None or now - current.window_start >= window:
        current = AttemptWindow(count=0, window_start=now)
    count = current.count + 1
    return AttemptWindow(
        count=count,
        window_start=current.window_start,
        locked_until=current.window_start + window if count >= limit else None,
    )
