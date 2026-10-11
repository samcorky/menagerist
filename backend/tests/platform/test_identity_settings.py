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
