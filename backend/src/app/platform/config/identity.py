from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Tunable
from app.platform.config._types import Cron  # noqa: TC001 - pydantic resolves this at runtime
from app.platform.config.api import get_api_settings
from app.platform.config.public_origin import public_is_https


class IdentitySettings(MenageristBaseSettings, group="identity"):
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
    purge_expired_schedule: Annotated[
        Cron,
        Field(
            title="Sign-in clean-up schedule",
            description=(
                "Cron expression for removing expired sessions and API tokens in the "
                + "instance timezone. Empty disables the job."
            ),
        ),
        Tunable(),
    ] = "15 4 * * *"
    cookie_name: str = Field(
        default="menagerist-session",
        min_length=1,
        pattern=r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$",
        description="Name of the HTTP-only session cookie.",
    )
    cookie_secure: Literal["auto", "origin", "always", "never"] = Field(
        default="auto",
        description=(
            "Secure session cookies: auto detects HTTPS from each request, origin"
            + " follows the scheme of api.public_origin, always and never force it."
        ),
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

    api_token_default_days: int = Field(
        default=90,
        ge=1,
        description="Lifetime in days offered for a new API token.",
    )
    api_token_max_days: int = Field(
        default=365,
        ge=1,
        description="Longest lifetime in days an API token may be given.",
    )
    api_tokens_per_user: int = Field(
        default=20,
        ge=1,
        description="Most active API tokens one person may hold.",
    )

    @model_validator(mode="after")
    def _default_within_max(self) -> IdentitySettings:
        if self.api_token_default_days > self.api_token_max_days:
            msg = "api_token_default_days must not exceed api_token_max_days"
            raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_identity_settings() -> IdentitySettings:
    """Return the cached identity settings.

    `cookie_secure = origin` is resolved here to `always` or `never` from the scheme
    of `api.public_origin`, so the cookie code only sees the three plain modes.

    Raises:
        ValueError: If `origin` is chosen but no public origin is set.
    """
    settings = IdentitySettings()
    if settings.cookie_secure != "origin":
        return settings
    https = public_is_https(get_api_settings())
    if https is None:
        msg = "COOKIE_SECURE=origin needs MENAGERIST_API_PUBLIC_ORIGIN to be set"
        raise ValueError(msg)
    return settings.model_copy(update={"cookie_secure": "always" if https else "never"})
