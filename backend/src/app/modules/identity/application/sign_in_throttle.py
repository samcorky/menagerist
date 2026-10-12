import hashlib
import math
import uuid  # noqa: TC003
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.modules.identity.domain.errors import SignInThrottledError
from app.modules.identity.domain.throttle import (
    AttemptWindow,
    ThrottleKey,
    ThrottleKind,
    ThrottlePolicy,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.identity.ports.sign_in_attempt_repository import (
        SignInAttemptRepository,
    )

THROTTLED_MESSAGE = "Too many failed attempts. Try again later."


def _key(kind: ThrottleKind, value: str) -> ThrottleKey:
    return ThrottleKey(kind=kind, digest=hashlib.sha256(value.encode()).hexdigest())


def username_key(username: str) -> ThrottleKey:
    """The counter for a username (any case), whether or not the account exists."""
    return _key(ThrottleKind.USERNAME, username.lower())


def user_id_key(user_id: uuid.UUID) -> ThrottleKey:
    """The counter for password checks made by a signed-in user."""
    return _key(ThrottleKind.USER_ID, str(user_id))


def ip_key(client_ip: str) -> ThrottleKey:
    """The counter for a client address."""
    return _key(ThrottleKind.IP, client_ip)


@dataclass(kw_only=True, frozen=True)
class Reservation:
    """Attempts counted before a password check, and any lock they hit."""

    windows: dict[ThrottleKey, AttemptWindow]
    locked_until: datetime | None = None


class SignInThrottle:
    """Fixed-window failure limits on password checks, per key and per address."""

    def __init__(self, policy: ThrottlePolicy | None = None) -> None:
        self.policy = policy or ThrottlePolicy()

    def limit_for(self, key: ThrottleKey) -> int:
        """Return how many failures `key` may make in one window."""
        if key.kind is ThrottleKind.IP:
            return self.policy.ip_limit
        return self.policy.username_limit

    def throttled(self, locked_until: datetime, now: datetime) -> SignInThrottledError:
        """Build the refusal for a lock that ends at `locked_until`."""
        return SignInThrottledError(
            THROTTLED_MESSAGE,
            retry_after=max(1, math.ceil((locked_until - now).total_seconds())),
        )

    async def reserve(
        self,
        attempts: SignInAttemptRepository,
        keys: Sequence[ThrottleKey],
        now: datetime,
    ) -> Reservation:
        """Count one attempt on each key before the password is checked.

        Counting is atomic per key, so parallel attempts cannot all pass a
        check made before any of them is recorded. `locked_until` is set when
        an attempt is past a limit and must be refused unchecked. Counters
        whose window ended are swept.
        """
        windows: dict[ThrottleKey, AttemptWindow] = {}
        locked_until: datetime | None = None
        for key in keys:
            limit = self.limit_for(key)
            current = await attempts.record_failure(
                key, limit=limit, window=self.policy.window, now=now
            )
            windows[key] = current
            if current.exceeds(limit):
                until = (
                    current.locked_until or current.window_start + self.policy.window
                )
                locked_until = (
                    until if locked_until is None else max(locked_until, until)
                )
        await attempts.delete_stale(window=self.policy.window, now=now)
        return Reservation(windows=windows, locked_until=locked_until)

    async def settle_success(
        self, attempts: SignInAttemptRepository, reservation: Reservation
    ) -> None:
        """Forget a correct check: clear the account's counter, refund the address's."""
        for key, window in reservation.windows.items():
            if key.kind is ThrottleKind.IP:
                await attempts.release_attempt(
                    key, window_start=window.window_start, limit=self.limit_for(key)
                )
            else:
                await attempts.clear(key)

    async def settle_refund(
        self, attempts: SignInAttemptRepository, reservation: Reservation
    ) -> None:
        """Give every counted attempt back (the check was right but led nowhere)."""
        for key, window in reservation.windows.items():
            await attempts.release_attempt(
                key, window_start=window.window_start, limit=self.limit_for(key)
            )
