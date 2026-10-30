import pytest
from pydantic import ValidationError

from app.platform.config import IdentitySettings


def test_defaults() -> None:
    """Defaults match the documented cookie and session settings."""
    settings = IdentitySettings()
    assert settings.session_ttl_hours == 168
    assert settings.session_idle_hours == 0
    assert settings.cookie_name == "menagerist-session"
    assert settings.cookie_secure == "auto"
    assert settings.password_hasher == "scrypt"


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Values come from `MENAGERIST_`-prefixed variables."""
    monkeypatch.setenv("MENAGERIST_IDENTITY_COOKIE_SECURE", "always")
    monkeypatch.setenv("MENAGERIST_IDENTITY_SESSION_TTL_HOURS", "2")
    settings = IdentitySettings()
    assert settings.cookie_secure == "always"
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
    monkeypatch.setenv("MENAGERIST_IDENTITY_SIGN_IN_USERNAME_ATTEMPTS", "3")
    monkeypatch.setenv("MENAGERIST_IDENTITY_SIGN_IN_IP_ATTEMPTS", "7")
    monkeypatch.setenv("MENAGERIST_IDENTITY_SIGN_IN_WINDOW_MINUTES", "1")
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
    monkeypatch.setenv("MENAGERIST_IDENTITY_PASSWORD_HASH_CONCURRENCY", "4")
    assert IdentitySettings().password_hash_concurrency == 4
    monkeypatch.setenv("MENAGERIST_IDENTITY_PASSWORD_HASH_CONCURRENCY", "0")
    with pytest.raises(ValidationError):
        IdentitySettings()


def test_idle_limit_is_configurable_and_never_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0 disables the idle limit; whole hours enable it; negatives are refused."""
    monkeypatch.setenv("MENAGERIST_IDENTITY_SESSION_IDLE_HOURS", "24")
    assert IdentitySettings().session_idle_hours == 24
    monkeypatch.setenv("MENAGERIST_IDENTITY_SESSION_IDLE_HOURS", "-1")
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
    monkeypatch.setenv(f"MENAGERIST_IDENTITY_{field.upper()}", value)
    with pytest.raises(ValidationError):
        IdentitySettings()


def test_password_hasher_must_be_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the password-hashing scheme wired into the application is accepted."""
    monkeypatch.setenv("MENAGERIST_IDENTITY_PASSWORD_HASHER", "unknown")
    with pytest.raises(ValidationError):
        IdentitySettings()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("MENAGERIST_IDENTITY_COOKIE_NAME", ""),
        ("MENAGERIST_IDENTITY_COOKIE_NAME", "invalid name"),
    ],
)
def test_cookie_names_must_be_valid_cookie_tokens(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    """Cookie names must be non-empty valid HTTP cookie tokens."""
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        IdentitySettings()


def test_a_leftover_csrf_cookie_name_variable_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployments still setting the removed variable start normally."""
    monkeypatch.setenv("MENAGERIST_CSRF_COOKIE_NAME", "menagerist-csrf")
    assert IdentitySettings().cookie_name == "menagerist-session"


def test_api_token_limits_default_and_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ninety days by default, a year at most, twenty tokens per person."""
    defaults = IdentitySettings()
    assert defaults.api_token_default_days == 90
    assert defaults.api_token_max_days == 365
    assert defaults.api_tokens_per_user == 20

    monkeypatch.setenv("MENAGERIST_IDENTITY_API_TOKEN_DEFAULT_DAYS", "30")
    monkeypatch.setenv("MENAGERIST_IDENTITY_API_TOKEN_MAX_DAYS", "60")
    monkeypatch.setenv("MENAGERIST_IDENTITY_API_TOKENS_PER_USER", "3")
    settings = IdentitySettings()
    assert settings.api_token_default_days == 30
    assert settings.api_token_max_days == 60
    assert settings.api_tokens_per_user == 3


def test_api_token_default_above_max_is_rejected() -> None:
    """A default lifetime longer than the maximum is a configuration error."""
    with pytest.raises(ValidationError):
        IdentitySettings(api_token_default_days=100, api_token_max_days=50)
