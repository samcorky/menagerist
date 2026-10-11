import hashlib
import math
import uuid  # noqa: TC003
from typing import TYPE_CHECKING

from app.modules.identity.domain.errors import SignInThrottledError
from app.modules.identity.domain.throttle import (
    ThrottleKey,
    ThrottleKind,
    ThrottlePolicy,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

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


class SignInThrottle:
    """Fixed-window failure limits on password checks, per key and per address."""

    def __init__(self, policy: ThrottlePolicy | None = None) -> None:
        self.policy = policy or ThrottlePolicy()

    def limit_for(self, key: ThrottleKey) -> int:
        """Return how many failures `key` may make in one window."""
        if key.kind is ThrottleKind.IP:
            return self.policy.ip_limit
        return self.policy.username_limit

    async def locked_until(
        self,
        attempts: SignInAttemptRepository,
        keys: Sequence[ThrottleKey],
        now: datetime,
    ) -> datetime | None:
        """Return when the latest lock among `keys` ends, or `None` if none."""
        locked = await attempts.locked_keys(keys, now=now)
        return max(locked.values(), default=None)

    def throttled(self, locked_until: datetime, now: datetime) -> SignInThrottledError:
        """Build the refusal for a lock that ends at `locked_until`."""
        return SignInThrottledError(
            THROTTLED_MESSAGE,
            retry_after=max(1, math.ceil((locked_until - now).total_seconds())),
        )

    async def ensure_open(
        self,
        attempts: SignInAttemptRepository,
        keys: Sequence[ThrottleKey],
        now: datetime,
    ) -> None:
        """Raise `SignInThrottledError` if any of `keys` is locked at `now`."""
        until = await self.locked_until(attempts, keys, now)
        if until is not None:
            raise self.throttled(until, now)

    async def record_failure(
        self,
        attempts: SignInAttemptRepository,
        keys: Sequence[ThrottleKey],
        now: datetime,
    ) -> None:
        """Count one failure on each key, and sweep counters whose window ended."""
        for key in keys:
            await attempts.record_failure(
                key, limit=self.limit_for(key), window=self.policy.window, now=now
            )
        await attempts.delete_stale(window=self.policy.window, now=now)
