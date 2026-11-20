"""The server's time zone: MENAGERIST_TIME_ZONE, then TZ, then UTC."""

import pytest
from pydantic import ValidationError

from app.platform.config import ServerSettings


@pytest.mark.parametrize(
    ("tz", "fallback", "expected"),
    [
        (None, None, "UTC"),
        ("Europe/London", "America/New_York", "America/New_York"),
        (None, "America/New_York", "America/New_York"),
        ("Europe/London", None, "Europe/London"),
        ("Europe/London", "", "Europe/London"),
        ("", "Europe/London", "Europe/London"),
        ("", "", "UTC"),
    ],
)
def test_timezone_precedence(
    monkeypatch: pytest.MonkeyPatch, tz: str | None, fallback: str | None, expected: str
) -> None:
    """MENAGERIST_TIME_ZONE overrides Docker's TZ; empty values fall through."""
    for name, value in [("TZ", tz), ("MENAGERIST_TIME_ZONE", fallback)]:
        monkeypatch.delenv(name, raising=False)
        if value is not None:
            monkeypatch.setenv(name, value)
    settings = ServerSettings()
    assert str(settings.time_zone) == expected
    assert settings.model_dump(mode="json")["time_zone"] == expected
    assert settings.source_of("time_zone") == (
        "default" if not tz and not fallback else "env"
    )


@pytest.mark.parametrize("zone", ["Not/AZone", "GMT+25"])
def test_invalid_timezone_is_a_validation_error(
    monkeypatch: pytest.MonkeyPatch, zone: str
) -> None:
    """Unknown zones fail at settings construction instead of worker execution."""
    monkeypatch.setenv("TZ", zone)
    with pytest.raises(ValidationError):
        ServerSettings()
