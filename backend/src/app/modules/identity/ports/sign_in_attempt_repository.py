from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime, timedelta

    from app.modules.identity.domain.throttle import AttemptWindow, ThrottleKey


class SignInAttemptRepository(Protocol):
    """Failure counters for password checks, independent of any account row."""

    async def locked_keys(
        self, keys: Sequence[ThrottleKey], *, now: datetime
    ) -> dict[ThrottleKey, datetime]:
        """Return, for each of `keys` that is locked at `now`, when its lock ends."""
        ...

    async def record_failure(
        self, key: ThrottleKey, *, limit: int, window: timedelta, now: datetime
    ) -> AttemptWindow:
        """Count one attempt atomically and return the counter after it.

        Callers count before checking a password and release on success (see
        `domain.throttle.after_failure`).
        """
        ...

    async def release_attempt(
        self, key: ThrottleKey, *, window_start: datetime, limit: int
    ) -> None:
        """Give back one attempt counted in the window `window_start`.

        A no-op if the key has none or its window has changed since.
        """
        ...

    async def clear(self, key: ThrottleKey) -> None:
        """Forget `key`'s failures and lock; a no-op if it has none."""
        ...

    async def delete_stale(self, *, window: timedelta, now: datetime) -> int:
        """Delete counters whose window ended by `now`; return how many."""
        ...
