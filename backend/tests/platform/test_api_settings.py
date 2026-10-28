import pytest
from pydantic import ValidationError

from app.platform.config.api import ApiSettings


def _settings(monkeypatch: pytest.MonkeyPatch, value: str | None) -> ApiSettings:
    if value is not None:
        monkeypatch.setenv("MENAGERIST_API_TRUSTED_PROXIES", value)
    return ApiSettings()


def test_default_trusts_only_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without configuration only the local proxy is believed."""
    monkeypatch.delenv("MENAGERIST_API_TRUSTED_PROXIES", raising=False)
    assert _settings(monkeypatch, None).trusted_proxies == ["127.0.0.1"]


def test_csv_of_addresses_and_networks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Addresses and networks are read from a CSV and kept as strings."""
    settings = _settings(monkeypatch, "10.0.0.1, 172.16.0.0/12 ,::1")
    assert settings.trusted_proxies == ["10.0.0.1", "172.16.0.0/12", "::1"]


def test_star_alone_trusts_everyone(monkeypatch: pytest.MonkeyPatch) -> None:
    """A lone wildcard means trust every peer."""
    assert _settings(monkeypatch, "*").trusted_proxies == ["*"]


@pytest.mark.parametrize(
    "bad", ["proxy.example.com", "10.0.0.256", "10.0.0.0/33", "10.0.0.1,*"]
)
def test_invalid_entries_are_rejected(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    """Hostnames and malformed addresses or networks fail validation."""
    with pytest.raises(ValidationError):
        _settings(monkeypatch, bad)


def test_cors_is_same_origin_only_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """No origin is allowed unless one is listed."""
    monkeypatch.delenv("MENAGERIST_API_CORS_ORIGINS", raising=False)
    assert ApiSettings().cors_origins == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("*", ["*"]),
        ("http://localhost:5173", ["http://localhost:5173"]),
        (
            "https://Menagerist.example.com/, http://[::1]:8000",
            ["https://menagerist.example.com", "http://[::1]:8000"],
        ),
        (
            "https://a.example:443,http://b.example:80",
            ["https://a.example", "http://b.example"],
        ),
    ],
)
def test_cors_origins_are_normalised_to_browser_form(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    """Origins lose trailing slashes and default ports, as browsers send them."""
    monkeypatch.setenv("MENAGERIST_API_CORS_ORIGINS", raw)
    assert ApiSettings().cors_origins == expected


@pytest.mark.parametrize(
    "bad",
    [
        "localhost:5173",
        "ftp://a.example",
        "https://a.example/app",
        "https://a.example/?x=1",
        "https://u@a.example",
        "https://a.example,*",
    ],
)
def test_cors_origins_reject_non_origins(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    """Paths, queries, credentials, other schemes and mixed wildcards fail fast."""
    monkeypatch.setenv("MENAGERIST_API_CORS_ORIGINS", bad)
    with pytest.raises(ValidationError):
        ApiSettings()
