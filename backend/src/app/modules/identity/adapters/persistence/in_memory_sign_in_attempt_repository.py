from typing import TYPE_CHECKING

from app.modules.identity.domain.throttle import after_failure, after_release

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime, timedelta

    from app.modules.identity.domain.throttle import AttemptWindow, ThrottleKey


class InMemorySignInAttemptRepository:
    """Dict-backed `SignInAttemptRepository` for tests."""

    def __init__(self) -> None:
        self.windows: dict[ThrottleKey, AttemptWindow] = {}

    async def locked_keys(
        self, keys: Sequence[ThrottleKey], *, now: datetime
    ) -> dict[ThrottleKey, datetime]:
        """Return, for each of `keys` that is locked at `now`, when its lock ends."""
        locked: dict[ThrottleKey, datetime] = {}
        for key in keys:
            current = self.windows.get(key)
            if (
                current is not None
                and current.locked_until is not None
                and now < current.locked_until
            ):
                locked[key] = current.locked_until
        return locked

    async def record_failure(
        self, key: ThrottleKey, *, limit: int, window: timedelta, now: datetime
    ) -> AttemptWindow:
        """Count one attempt."""
        updated = after_failure(
            self.windows.get(key), now=now, limit=limit, window=window
        )
        self.windows[key] = updated
        return updated

    async def release_attempt(
        self, key: ThrottleKey, *, window_start: datetime, limit: int
    ) -> None:
        """Give back one attempt of the window `window_start`."""
        current = self.windows.get(key)
        updated = after_release(current, window_start=window_start, limit=limit)
        if updated is not None:
            self.windows[key] = updated

    async def clear(self, key: ThrottleKey) -> None:
        """Forget `key`'s failures and lock."""
        self.windows.pop(key, None)

    async def delete_stale(self, *, window: timedelta, now: datetime) -> int:
        """Delete counters whose window ended by `now`."""
        stale = [
            key
            for key, current in self.windows.items()
            if now - current.window_start >= window
        ]
        for key in stale:
            del self.windows[key]
        return len(stale)
