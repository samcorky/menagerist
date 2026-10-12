import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.shared_kernel.mixins import Identifiable


@dataclass(kw_only=True, eq=False)
class Session(Identifiable):
    """A signed-in browser, identified by the hash of its secret token."""

    user_id: uuid.UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime

    @classmethod
    def create(
        cls, *, user_id: uuid.UUID, token_hash: str, now: datetime, ttl: timedelta
    ) -> Session:
        """Create a session that expires `ttl` after `now`."""
        return cls(
            id=uuid.uuid7(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + ttl,
            last_seen_at=now,
        )

    def seen(self, now: datetime) -> None:
        """Record activity at `now`."""
        self.last_seen_at = now

    def is_expired(self, now: datetime) -> bool:
        """Whether `now` is at or past the expiry instant."""
        return now >= self.expires_at

    def is_idle(self, now: datetime, limit: timedelta | None) -> bool:
        """Whether more than `limit` has passed since the session was last seen.

        `None` means no idle limit.
        """
        return limit is not None and now - self.last_seen_at > limit
