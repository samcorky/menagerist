import re
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator

from app.platform.config._base import MenageristBaseSettings

# Printable ASCII only, and none of the characters that would end the User-Agent
# comment early or start another one.
_HEADER_SAFE = re.compile(r"[ -~]*")
_FORBIDDEN_IN_HEADER_TEXT = "();"
MAX_CONTACT_LENGTH = 200
MAX_NOTE_LENGTH = 100
_PROXY_SCHEMES = frozenset({"http", "https"})


class OutboundHttpSettings(MenageristBaseSettings, group="http"):
    """How Menagerist behaves when it calls out to other web services."""

    contact: str = Field(
        default="",
        description=(
            "An email address or web address added to the User-Agent of every "
            + "outbound request, so a service that throttles this instance can reach "
            + "you. Empty sends no contact. Plain text only: no brackets or "
            + "semicolons."
        ),
    )
    user_agent_note: str = Field(
        default="",
        description=(
            "A short note added to the User-Agent of every outbound request after "
            + "the contact, for example `self-hosted`. Empty adds nothing. Plain "
            + "text only: no brackets or semicolons."
        ),
    )
    http_proxy: SecretStr | None = Field(
        default=None,
        validation_alias="HTTP_PROXY",
        description=(
            "Proxy for outbound `http://` requests, as `http://host:port` with "
            + "optional `user:password@`. Empty uses none. The standard "
            + "`HTTP_PROXY` name."
        ),
    )
    https_proxy: SecretStr | None = Field(
        default=None,
        validation_alias="HTTPS_PROXY",
        description=(
            "Proxy for outbound `https://` requests, as `http://host:port` with "
            + "optional `user:password@`. Empty uses none. The standard "
            + "`HTTPS_PROXY` name."
        ),
    )
    no_proxy: str = Field(
        default="",
        validation_alias="NO_PROXY",
        max_length=1000,
        description=(
            "Comma-separated host names, domains (`example.com` also matches its "
            + "subdomains), IP addresses and network ranges that skip the proxy, "
            + "or `*` for all. The standard `NO_PROXY` name."
        ),
    )
    connect_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=120,
        description="Seconds to wait for a connection to an outbound service.",
    )
    read_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=300,
        description="Seconds to wait for each part of an outbound service's reply.",
    )
    max_response_bytes: int = Field(
        default=2 * 1024 * 1024,
        ge=1024,
        description=(
            "Largest reply, in bytes, accepted from an outbound service unless the "
            + "caller asks for a smaller one."
        ),
    )

    @field_validator("contact")
    @classmethod
    def _contact_is_header_safe(cls, value: str) -> str:
        return _header_safe(value, MAX_CONTACT_LENGTH)

    @field_validator("user_agent_note")
    @classmethod
    def _note_is_header_safe(cls, value: str) -> str:
        return _header_safe(value, MAX_NOTE_LENGTH)

    @field_validator("http_proxy", "https_proxy")
    @classmethod
    def _proxy_is_a_web_address(cls, value: SecretStr | None) -> SecretStr | None:
        text = value.get_secret_value().strip() if value else ""
        if not text:
            return None
        try:
            parts = urlsplit(text)
            usable = parts.scheme in _PROXY_SCHEMES and bool(parts.hostname)
            _ = parts.port  # raises for a port that is not a number
        except ValueError:
            usable = False
        if not usable:
            message = "must be an http:// or https:// address with a host"
            raise ValueError(message)
        return SecretStr(text)


def _header_safe(value: str, max_length: int) -> str:
    text = value.strip()
    if (
        len(text) > max_length
        or not _HEADER_SAFE.fullmatch(text)
        or any(char in text for char in _FORBIDDEN_IN_HEADER_TEXT)
    ):
        message = (
            f"must be at most {max_length} printable ASCII characters "
            + "with no brackets or semicolons"
        )
        raise ValueError(message)
    return text


@lru_cache(maxsize=1)
def get_outbound_http_settings() -> OutboundHttpSettings:
    """Return the cached outbound HTTP settings."""
    return OutboundHttpSettings()
