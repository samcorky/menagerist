import pytest
from pydantic import ValidationError

from app.platform.config.outbound_http import (
    MAX_CONTACT_LENGTH,
    OutboundHttpSettings,
    get_outbound_http_settings,
)


def test_the_defaults_send_no_contact_and_bound_every_request() -> None:
    """The defaults send no contact and bound every request."""
    settings = OutboundHttpSettings()

    assert settings.contact == ""
    assert settings.connect_timeout_seconds == 5.0
    assert settings.read_timeout_seconds == 10.0
    assert settings.max_response_bytes == 2 * 1024 * 1024


def test_the_contact_is_read_from_its_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The contact is read from its environment variable."""
    monkeypatch.setenv("MENAGERIST_HTTP_CONTACT", "  me@example.com ")

    assert OutboundHttpSettings().contact == "me@example.com"


@pytest.mark.parametrize(
    "contact",
    [
        "a\r\nX-Injected: 1",
        "tab\there",
        "café@example.com",
        "me (at) example.com",
        "me; other",
        "x" * (MAX_CONTACT_LENGTH + 1),
    ],
)
def test_a_contact_that_could_break_the_header_is_refused(contact: str) -> None:
    """A contact that could break the header is refused."""
    with pytest.raises(ValidationError):
        OutboundHttpSettings(contact=contact)


@pytest.mark.parametrize(
    "limits",
    [
        {"connect_timeout_seconds": 0},
        {"read_timeout_seconds": 301},
        {"max_response_bytes": 10},
    ],
)
def test_limits_outside_their_range_are_refused(limits: dict[str, float]) -> None:
    """Limits outside their range are refused."""
    with pytest.raises(ValidationError):
        OutboundHttpSettings(**limits)  # type: ignore[arg-type]


def test_the_settings_are_cached() -> None:
    """The settings are cached."""
    assert get_outbound_http_settings() is get_outbound_http_settings()
