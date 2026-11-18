import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.modules.identity.domain.errors import InvalidDeviceNameError
from app.modules.identity.domain.session import (
    MAX_CLIENT_PLATFORM_LENGTH,
    MAX_USER_AGENT_LENGTH,
    DisplayMode,
    clean_text,
)
from app.shared_kernel.mixins import Identifiable

MAX_DEVICE_NAME_LENGTH = 60

# Checked in order: browsers built on another browser's engine also name that
# engine (Edge says "Chrome", Chrome on iOS says "Safari"), so the specific
# markers come first. Versions are deliberately not captured.
_BROWSER_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Edge", re.compile(r"\b(?:Edg|EdgA|EdgiOS|Edge)/")),
    ("Opera", re.compile(r"\b(?:OPR|OPT|OPiOS)/|\bOpera\b")),
    ("Samsung Internet", re.compile(r"\bSamsungBrowser/")),
    ("Firefox", re.compile(r"\b(?:Firefox|FxiOS)/")),
    ("Chrome", re.compile(r"\b(?:Chrome|CriOS|Chromium)/")),
    ("Safari", re.compile(r"\bSafari/")),
)


def browser_family(user_agent: str | None) -> str | None:
    """Name the browser behind `user_agent` without its version, or `None`.

    Versions change with every update, so only the family is used to decide
    whether two devices are the same kind of browser.
    """
    if not user_agent:
        return None
    return next(
        (name for name, marker in _BROWSER_MARKERS if marker.search(user_agent)),
        None,
    )


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
    display_mode: DisplayMode | None = None
    name: str | None = None

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
        display_mode: DisplayMode | None = None,
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
            now,
            ttl=ttl,
            user_agent=user_agent,
            platform=platform,
            mobile=mobile,
            display_mode=display_mode,
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
        display_mode: DisplayMode | None = None,
    ) -> None:
        """Record a sign-in at `now` with the browser's current details.

        Being the installed app sticks: a browser-tab or missing display mode
        never clears it, because the header is absent on older clients and the
        same device signs in from both the installed app and a tab.
        """
        self.last_seen_at = now
        self.expires_at = now + ttl
        self.user_agent = clean_text(user_agent, MAX_USER_AGENT_LENGTH)
        self.platform = clean_text(platform, MAX_CLIENT_PLATFORM_LENGTH)
        self.mobile = mobile
        if display_mode is DisplayMode.STANDALONE or self.display_mode is None:
            self.display_mode = display_mode

    def rename(self, name: str | None) -> None:
        """Give the device a name, or clear it with a blank one.

        Raises:
            InvalidDeviceNameError: If the trimmed name is too long.
        """
        trimmed = (name or "").strip()
        if len(trimmed) > MAX_DEVICE_NAME_LENGTH:
            raise InvalidDeviceNameError(
                f"A device name can be at most {MAX_DEVICE_NAME_LENGTH} characters."
            )
        self.name = trimmed or None

    @property
    def installed(self) -> bool:
        """Whether this browser has signed in as the installed app."""
        return self.display_mode is DisplayMode.STANDALONE

    def is_same_kind_of_browser(self, other: Device) -> bool:
        """Whether `other` is the same browser family, platform, mobile flag and kind.

        A suggestion aid only: nothing reliably identifies a browser once its
        cookie is gone. A missing family, platform or mobile flag never matches.
        The installed app and a browser tab are different kinds, so neither is
        offered the other's name.
        """
        family = browser_family(self.user_agent)
        return (
            family is not None
            and self.platform is not None
            and self.mobile is not None
            and family == browser_family(other.user_agent)
            and self.platform == other.platform
            and self.mobile == other.mobile
            and self.installed == other.installed
        )

    def is_expired(self, now: datetime) -> bool:
        """Whether `now` is at or past the expiry instant."""
        return now >= self.expires_at
