from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator

from app.platform.config._base import MenageristBaseSettings


class IdentitySettings(MenageristBaseSettings):
    """Configuration for the identity module."""

    session_ttl_hours: int = Field(
        default=168,
        ge=1,
        description="Maximum lifetime of a session in hours, even while it is active.",
    )
    session_idle_hours: int = Field(
        default=0,
        ge=0,
        description="Idle timeout in hours; 0 disables this limit.",
    )
    cookie_name: str = Field(
        default="menagerist-session",
        min_length=1,
        pattern=r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$",
        description="Name of the HTTP-only session cookie.",
    )
    csrf_cookie_name: str = Field(
        default="menagerist-csrf",
        min_length=1,
        pattern=r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$",
        description="Name of the cookie containing the CSRF token.",
    )
    cookie_secure: bool | None = Field(
        default=None,
        description="Secure session cookies; unset detects HTTPS from requests.",
    )
    password_hasher: Literal["scrypt"] = Field(
        default="scrypt",
        description="Password-hashing scheme used for newly created password hashes.",
    )
    sign_in_username_attempts: int = Field(
        default=5,
        ge=1,
        description="Failed sign-ins allowed per username in each throttle window.",
    )
    sign_in_ip_attempts: int = Field(
        default=20,
        ge=1,
        description="Failed sign-ins allowed per IP address in each throttle window.",
    )
    sign_in_window_minutes: int = Field(
        default=15,
        ge=1,
        description="Duration of the failed sign-in throttle window in minutes.",
    )
    password_hash_concurrency: int = Field(
        default=2,
        ge=1,
        description=(
            "Maximum number of simultaneous password-hash operations in this process."
        ),
    )

    @model_validator(mode="after")
    def validate_cookie_names_are_distinct(self) -> Self:
        """Require separate names so the session and CSRF cookies do not collide."""
        if self.cookie_name == self.csrf_cookie_name:
            raise ValueError("Session and CSRF cookie names must be different.")
        return self


@lru_cache(maxsize=1)
def get_identity_settings() -> IdentitySettings:
    """Return the cached identity settings."""
    return IdentitySettings()
