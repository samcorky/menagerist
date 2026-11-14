import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.shared_kernel.mixins import Identifiable

MAX_USER_AGENT_LENGTH = 256
MAX_CLIENT_PLATFORM_LENGTH = 64


class DisplayMode(StrEnum):
    """How the app was shown when a session started: a browser tab or installed."""

    BROWSER = "browser"
    STANDALONE = "standalone"


def clean_text(value: str | None, limit: int) -> str | None:
    """Strip `value` and cut it to `limit` characters; blank gives `None`."""
    cleaned = value.strip() if value else None
    return cleaned[:limit] if cleaned else None


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
    device_id: uuid.UUID | None = None
    display_mode: DisplayMode | None = None

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
        device_id: uuid.UUID | None = None,
        display_mode: DisplayMode | None = None,
    ) -> Session:
        """Create a session that expires `ttl` after `now`."""
        cleaned_ip = client_ip.strip() if client_ip else None
        return cls(
            id=uuid.uuid7(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + ttl,
            last_seen_at=now,
            user_agent=clean_text(user_agent, MAX_USER_AGENT_LENGTH),
            client_ip=cleaned_ip or None,
            client_platform=clean_text(client_platform, MAX_CLIENT_PLATFORM_LENGTH),
            client_mobile=client_mobile,
            device_id=device_id,
            display_mode=display_mode,
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
