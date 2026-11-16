import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.identity.domain.device import (
    MAX_DEVICE_NAME_LENGTH,
    Device,
    browser_family,
)
from app.modules.identity.domain.errors import InvalidDeviceNameError
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


def test_a_new_device_has_no_name() -> None:
    """Naming is optional, so a remembered browser starts unnamed."""
    assert _device().name is None


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("Sam's phone", "Sam's phone"),
        ("  Work laptop  ", "Work laptop"),
        ("", None),
        ("   ", None),
        (None, None),
        ("x" * MAX_DEVICE_NAME_LENGTH, "x" * MAX_DEVICE_NAME_LENGTH),
    ],
)
def test_rename_strips_and_clears_blank_names(
    given: str | None, stored: str | None
) -> None:
    """A blank name clears it; anything else is stored trimmed."""
    device = _device()
    device.name = "Old"

    device.rename(given)

    assert device.name == stored


def test_rename_refuses_a_name_that_is_too_long() -> None:
    """The limit is on the trimmed name, and the old name is kept on refusal."""
    device = _device()
    device.name = "Old"

    with pytest.raises(InvalidDeviceNameError):
        device.rename("x" * (MAX_DEVICE_NAME_LENGTH + 1))

    assert device.name == "Old"


def test_seen_keeps_the_name() -> None:
    """Signing in again on the same browser does not lose its name."""
    device = _device()
    device.rename("Sam's phone")

    device.seen(NOW + timedelta(days=1), ttl=TTL, user_agent="Firefox")

    assert device.name == "Sam's phone"


FIREFOX_130 = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
FIREFOX_131 = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"


def _webkit(system: str, tail: str) -> str:
    """Build a WebKit-style user agent for `system` ending in `tail`."""
    return " ".join(
        [f"Mozilla/5.0 ({system})", "AppleWebKit/537.36 (KHTML, like Gecko)", tail]
    )


@pytest.mark.parametrize(
    ("user_agent", "family"),
    [
        (FIREFOX_130, "Firefox"),
        (_webkit("iPhone; CPU iPhone OS 17_5 like Mac OS X", "FxiOS/130.0"), "Firefox"),
        (
            _webkit("Windows NT 10.0; Win64; x64", "Chrome/129.0.0.0 Safari/537.36"),
            "Chrome",
        ),
        (
            _webkit("iPhone; CPU iPhone OS 17_5 like Mac OS X", "CriOS/129.0.0.0"),
            "Chrome",
        ),
        (
            _webkit("Windows NT 10.0", "Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"),
            "Edge",
        ),
        (
            _webkit("Windows NT 10.0", "Chrome/129.0.0.0 Safari/537.36 OPR/114.0.0.0"),
            "Opera",
        ),
        (
            _webkit("Linux; Android 14", "SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile"),
            "Samsung Internet",
        ),
        (
            _webkit(
                "Macintosh; Intel Mac OS X 10_15_7", "Version/17.5 Safari/605.1.15"
            ),
            "Safari",
        ),
        ("curl/8.5.0", None),
        ("", None),
        (None, None),
    ],
)
def test_browser_family_ignores_versions(
    user_agent: str | None, family: str | None
) -> None:
    """The family names the browser, not its version, so updates keep matching."""
    assert browser_family(user_agent) == family


CHROME_129 = _webkit("X11; Linux x86_64", "Chrome/129.0.0.0 Safari/537.36")


def _browser(
    user_agent: str | None, platform: str | None, *, mobile: bool | None
) -> Device:
    return Device.create(
        user_id=uuid.uuid7(),
        token_hash="hash",
        now=NOW,
        ttl=TTL,
        user_agent=user_agent,
        platform=platform,
        mobile=mobile,
    )


def test_same_browser_ignores_the_version() -> None:
    """A browser update does not stop a device matching its older self."""
    old = _browser(FIREFOX_130, "Linux", mobile=False)
    new = _browser(FIREFOX_131, "Linux", mobile=False)

    assert new.is_same_kind_of_browser(old)


@pytest.mark.parametrize(
    ("other_agent", "other_platform", "other_mobile"),
    [
        (CHROME_129, "Linux", False),
        (FIREFOX_130, "Windows", False),
        (FIREFOX_130, "Linux", True),
        (FIREFOX_130, "Linux", None),
        (FIREFOX_130, None, False),
    ],
)
def test_different_family_platform_or_mobile_flag_never_match(
    other_agent: str, other_platform: str | None, other_mobile: bool | None
) -> None:
    """Browser family, platform and the mobile flag must all agree."""
    here = _browser(FIREFOX_130, "Linux", mobile=False)
    other = _browser(other_agent, other_platform, mobile=other_mobile)

    assert not here.is_same_kind_of_browser(other)


def test_a_browser_with_no_known_family_matches_nothing() -> None:
    """Without a family there is nothing reliable to match on."""
    unknown = _browser("curl/8.5.0", "Linux", mobile=False)

    assert not unknown.is_same_kind_of_browser(unknown)


def test_a_browser_with_no_known_platform_matches_nothing() -> None:
    """A missing platform is not evidence that two browsers are the same kind."""
    no_platform = _browser(FIREFOX_130, None, mobile=False)

    assert not no_platform.is_same_kind_of_browser(no_platform)
