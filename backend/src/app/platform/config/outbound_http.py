import re
from functools import lru_cache

from pydantic import Field, field_validator

from app.platform.config._base import MenageristBaseSettings

# Printable ASCII only, and none of the characters that would end the User-Agent
# comment early or start another one.
_CONTACT = re.compile(r"[ -~]*")
_FORBIDDEN_IN_CONTACT = "();"
MAX_CONTACT_LENGTH = 200


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
        contact = value.strip()
        if (
            len(contact) > MAX_CONTACT_LENGTH
            or not _CONTACT.fullmatch(contact)
            or any(char in contact for char in _FORBIDDEN_IN_CONTACT)
        ):
            message = (
                f"must be at most {MAX_CONTACT_LENGTH} printable ASCII characters "
                + "with no brackets or semicolons"
            )
            raise ValueError(message)
        return contact


@lru_cache(maxsize=1)
def get_outbound_http_settings() -> OutboundHttpSettings:
    """Return the cached outbound HTTP settings."""
    return OutboundHttpSettings()
