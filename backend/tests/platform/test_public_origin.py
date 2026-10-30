"""Values other settings fall back to when `api.public_origin` is set."""

from typing import TYPE_CHECKING

import pytest

from app.platform.config import get_api_settings, get_identity_settings
from app.platform.config.api import ApiSettings
from app.platform.config.public_origin import public_host, public_is_https

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.platform.config.identity import IdentitySettings


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_api_settings.cache_clear()
    get_identity_settings.cache_clear()
    yield
    get_api_settings.cache_clear()
    get_identity_settings.cache_clear()


def _api(monkeypatch: pytest.MonkeyPatch, origin: str | None) -> ApiSettings:
    if origin is None:
        monkeypatch.delenv("MENAGERIST_API_PUBLIC_ORIGIN", raising=False)
    else:
        monkeypatch.setenv("MENAGERIST_API_PUBLIC_ORIGIN", origin)
    return ApiSettings()


def test_nothing_is_derived_without_a_public_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No address set: the host and scheme are unknown, not guessed."""
    api = _api(monkeypatch, None)

    assert public_host(api) is None
    assert public_is_https(api) is None


@pytest.mark.parametrize(
    ("origin", "host", "https"),
    [
        ("https://menagerist.example.com", "menagerist.example.com", True),
        ("http://localhost:8080", "localhost", False),
        ("https://[::1]:8443", "::1", True),
    ],
)
def test_host_and_scheme_come_from_the_origin(
    monkeypatch: pytest.MonkeyPatch, origin: str, host: str, https: bool
) -> None:
    """The host has no port or brackets; the scheme says whether it is HTTPS."""
    api = _api(monkeypatch, origin)

    assert public_host(api) == host
    assert public_is_https(api) is https


def _identity(
    monkeypatch: pytest.MonkeyPatch, origin: str | None, mode: str | None
) -> IdentitySettings:
    if origin is not None:
        monkeypatch.setenv("MENAGERIST_API_PUBLIC_ORIGIN", origin)
    if mode is not None:
        monkeypatch.setenv("MENAGERIST_IDENTITY_COOKIE_SECURE", mode)
    return get_identity_settings()


def test_cookie_secure_defaults_to_auto_whatever_the_public_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting the address does not change cookie behaviour by itself."""
    monkeypatch.delenv("MENAGERIST_IDENTITY_COOKIE_SECURE", raising=False)

    assert (
        _identity(monkeypatch, "https://menagerist.example.com", None).cookie_secure
        == "auto"
    )


@pytest.mark.parametrize(
    ("origin", "expected"),
    [("https://menagerist.example.com", "always"), ("http://localhost:8080", "never")],
)
def test_origin_mode_follows_the_public_origin_scheme(
    monkeypatch: pytest.MonkeyPatch, origin: str, expected: str
) -> None:
    """`origin` makes the cookie Secure exactly when the public address is HTTPS."""
    assert _identity(monkeypatch, origin, "origin").cookie_secure == expected


def test_origin_mode_needs_a_public_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Asking to follow an address that is not set stops start-up, naming both."""
    monkeypatch.delenv("MENAGERIST_API_PUBLIC_ORIGIN", raising=False)
    monkeypatch.setenv("MENAGERIST_IDENTITY_COOKIE_SECURE", "origin")

    with pytest.raises(ValueError, match="MENAGERIST_API_PUBLIC_ORIGIN"):
        get_identity_settings()


@pytest.mark.parametrize("mode", ["always", "never"])
def test_explicit_modes_ignore_the_public_origin(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """`always` and `never` are the person's word, whatever the address says."""
    assert (
        _identity(monkeypatch, "https://menagerist.example.com", mode).cookie_secure
        == mode
    )
