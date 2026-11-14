import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.modules.identity.domain.session import (
    MAX_CLIENT_PLATFORM_LENGTH,
    MAX_USER_AGENT_LENGTH,
    clean_text,
)
from app.shared_kernel.mixins import Identifiable


@dataclass(kw_only=True, eq=False)
class Device(Identifiable):
    """A browser remembered for one account by a long-lived device cookie.

    Only the hash of the cookie's secret is stored. Sessions started in the
    browser link to it, and a browser presenting it signs in under its own,
    higher failure limit instead of the username's.
    """

    user_id: uuid.UUID
    token_hash: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None = None
    platform: str | None = None
    mobile: bool | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        now: datetime,
        ttl: timedelta,
        user_agent: str | None = None,
        platform: str | None = None,
        mobile: bool | None = None,
    ) -> Device:
        """Remember a browser first seen at `now`, for `ttl` after its last sign-in."""
        device = cls(
            id=uuid.uuid7(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            last_seen_at=now,
            expires_at=now + ttl,
        )
        device.seen(
            now, ttl=ttl, user_agent=user_agent, platform=platform, mobile=mobile
        )
        return device

    def seen(
        self,
        now: datetime,
        *,
        ttl: timedelta,
        user_agent: str | None = None,
        platform: str | None = None,
        mobile: bool | None = None,
    ) -> None:
        """Record a sign-in at `now` with the browser's current details."""
        self.last_seen_at = now
        self.expires_at = now + ttl
        self.user_agent = clean_text(user_agent, MAX_USER_AGENT_LENGTH)
        self.platform = clean_text(platform, MAX_CLIENT_PLATFORM_LENGTH)
        self.mobile = mobile

    def is_expired(self, now: datetime) -> bool:
        """Whether `now` is at or past the expiry instant."""
        return now >= self.expires_at
