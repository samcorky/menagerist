import pytest
from pydantic import ValidationError

from app.platform.config import IdentitySettings


def test_defaults() -> None:
    """Defaults match the documented cookie and session settings."""
    settings = IdentitySettings()
    assert settings.session_ttl_hours == 168
    assert settings.session_idle_hours == 0
    assert settings.cookie_name == "menagerist-session"
    assert settings.csrf_cookie_name == "menagerist-csrf"
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_ttl_hours", "0"),
        ("sign_in_username_attempts", "0"),
        ("sign_in_ip_attempts", "0"),
        ("sign_in_window_minutes", "0"),
        ("password_hash_concurrency", "0"),
    ],
)
def test_positive_identity_limits_reject_zero(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    """Session lifetime, throttle limits and hashing concurrency must be positive."""
    monkeypatch.setenv(f"MENAGERIST_{field.upper()}", value)
    with pytest.raises(ValidationError):
        IdentitySettings()


def test_password_hasher_must_be_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the password-hashing scheme wired into the application is accepted."""
    monkeypatch.setenv("MENAGERIST_PASSWORD_HASHER", "unknown")
    with pytest.raises(ValidationError):
        IdentitySettings()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("MENAGERIST_COOKIE_NAME", ""),
        ("MENAGERIST_COOKIE_NAME", "invalid name"),
        ("MENAGERIST_CSRF_COOKIE_NAME", "invalid;name"),
    ],
)
def test_cookie_names_must_be_valid_cookie_tokens(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    """Cookie names must be non-empty valid HTTP cookie tokens."""
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        IdentitySettings()


def test_session_and_csrf_cookie_names_must_differ() -> None:
    """The browser must be able to distinguish the session and CSRF cookies."""
    with pytest.raises(ValidationError):
        IdentitySettings(cookie_name="same", csrf_cookie_name="same")
