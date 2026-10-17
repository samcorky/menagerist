import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.shared_kernel.mixins import Identifiable

MAX_USER_AGENT_LENGTH = 256
MAX_CLIENT_PLATFORM_LENGTH = 64


@dataclass(kw_only=True, eq=False)
class Session(Identifiable):
    """A signed-in browser, identified by the hash of its secret token."""

    user_id: uuid.UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    user_agent: str | None = None
    client_ip: str | None = None
    client_platform: str | None = None
    client_mobile: bool | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        now: datetime,
        ttl: timedelta,
        user_agent: str | None = None,
        client_ip: str | None = None,
        client_platform: str | None = None,
        client_mobile: bool | None = None,
    ) -> Session:
        """Create a session that expires `ttl` after `now`."""
        cleaned_ua = user_agent.strip() if user_agent else None
        cleaned_ua = cleaned_ua[:MAX_USER_AGENT_LENGTH] if cleaned_ua else None

        cleaned_platform = client_platform.strip() if client_platform else None
        cleaned_platform = (
            cleaned_platform[:MAX_CLIENT_PLATFORM_LENGTH] if cleaned_platform else None
        )

        cleaned_ip = client_ip.strip() if client_ip else None
        cleaned_ip = cleaned_ip if cleaned_ip else None

        return cls(
            id=uuid.uuid7(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + ttl,
            last_seen_at=now,
            user_agent=cleaned_ua,
            client_ip=cleaned_ip,
            client_platform=cleaned_platform,
            client_mobile=client_mobile,
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
