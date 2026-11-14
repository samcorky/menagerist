from datetime import UTC, datetime, timedelta

import pytest

from app.modules.identity.domain.device import Device
from app.modules.identity.domain.session import (
    MAX_CLIENT_PLATFORM_LENGTH,
    MAX_USER_AGENT_LENGTH,
    clean_text,
)
from app.modules.identity.domain.user import User

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
TTL = timedelta(days=365)


def _device() -> Device:
    owner = User.create(
        username="alice", display_name="Alice", password_hash="x", now=NOW
    )
    return Device.create(
        user_id=owner.id,
        token_hash="hash",
        now=NOW,
        ttl=TTL,
        user_agent="  Firefox  ",
        platform="Linux",
        mobile=False,
    )


def test_create_cleans_details_and_sets_the_lifetime() -> None:
    """A new device is first and last seen now, and lives `ttl` from now."""
    device = _device()

    assert device.created_at == device.last_seen_at == NOW
    assert device.expires_at == NOW + TTL
    assert device.user_agent == "Firefox"
    assert device.platform == "Linux"
    assert device.mobile is False


def test_seen_moves_last_seen_and_expiry_and_replaces_details() -> None:
    """A later sign-in refreshes the details and extends the lifetime."""
    device = _device()
    later = NOW + timedelta(days=10)

    device.seen(
        later,
        ttl=TTL,
        user_agent="x" * (MAX_USER_AGENT_LENGTH + 5),
        platform="  ",
        mobile=True,
    )

    assert device.created_at == NOW
    assert device.last_seen_at == later
    assert device.expires_at == later + TTL
    assert device.user_agent == "x" * MAX_USER_AGENT_LENGTH
    assert device.platform is None
    assert device.mobile is True


@pytest.mark.parametrize(
    ("offset", "expired"),
    [(TTL - timedelta(seconds=1), False), (TTL, True), (TTL * 2, True)],
)
def test_is_expired_at_and_after_the_expiry(offset: timedelta, expired: bool) -> None:
    """Expiry is inclusive of the expiry instant."""
    assert _device().is_expired(NOW + offset) is expired


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("  Linux ", "Linux"),
        ("y" * (MAX_CLIENT_PLATFORM_LENGTH + 1), "y" * MAX_CLIENT_PLATFORM_LENGTH),
    ],
)
def test_clean_text(value: str | None, expected: str | None) -> None:
    """Blank becomes None; the rest is stripped and capped."""
    assert clean_text(value, MAX_CLIENT_PLATFORM_LENGTH) == expected
