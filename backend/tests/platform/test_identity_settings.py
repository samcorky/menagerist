from typing import TYPE_CHECKING

from app.platform.config import IdentitySettings

if TYPE_CHECKING:
    import pytest


def test_defaults() -> None:
    """Defaults match the documented cookie and session settings."""
    settings = IdentitySettings()
    assert settings.session_ttl_hours == 168
    assert settings.cookie_name == "menagerist_session"
    assert settings.csrf_cookie_name == "menagerist_csrf"
    assert settings.cookie_secure is None
    assert settings.password_hasher == "scrypt"


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Values come from `MENAGERIST_`-prefixed variables."""
    monkeypatch.setenv("MENAGERIST_COOKIE_SECURE", "true")
    monkeypatch.setenv("MENAGERIST_SESSION_TTL_HOURS", "2")
    settings = IdentitySettings()
    assert settings.cookie_secure is True
    assert settings.session_ttl_hours == 2


def test_sign_in_limits_default_and_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five per username and twenty per address in fifteen minutes by default."""
    defaults = IdentitySettings()
    assert (
        defaults.sign_in_username_attempts,
        defaults.sign_in_ip_attempts,
        defaults.sign_in_window_minutes,
    ) == (5, 20, 15)
    monkeypatch.setenv("MENAGERIST_SIGN_IN_USERNAME_ATTEMPTS", "3")
    monkeypatch.setenv("MENAGERIST_SIGN_IN_IP_ATTEMPTS", "7")
    monkeypatch.setenv("MENAGERIST_SIGN_IN_WINDOW_MINUTES", "1")
    tuned = IdentitySettings()
    assert (
        tuned.sign_in_username_attempts,
        tuned.sign_in_ip_attempts,
        tuned.sign_in_window_minutes,
    ) == (3, 7, 1)
