import pytest
from pydantic import ValidationError

from app.platform.config import IdentitySettings


def test_defaults() -> None:
    """Defaults match the documented cookie and session settings."""
    settings = IdentitySettings()
    assert settings.session_ttl_hours == 168
    assert settings.session_idle_hours == 0
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


def test_password_hash_concurrency_defaults_to_two_and_is_at_least_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two hashes at a time by default; zero is refused."""
    assert IdentitySettings().password_hash_concurrency == 2
    monkeypatch.setenv("MENAGERIST_PASSWORD_HASH_CONCURRENCY", "4")
    assert IdentitySettings().password_hash_concurrency == 4
    monkeypatch.setenv("MENAGERIST_PASSWORD_HASH_CONCURRENCY", "0")
    with pytest.raises(ValidationError):
        IdentitySettings()


def test_idle_limit_is_configurable_and_never_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0 disables the idle limit; whole hours enable it; negatives are refused."""
    monkeypatch.setenv("MENAGERIST_SESSION_IDLE_HOURS", "24")
    assert IdentitySettings().session_idle_hours == 24
    monkeypatch.setenv("MENAGERIST_SESSION_IDLE_HOURS", "-1")
    with pytest.raises(ValidationError):
        IdentitySettings()
