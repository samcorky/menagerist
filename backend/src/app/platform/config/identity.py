from functools import lru_cache

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings


class IdentitySettings(MenageristBaseSettings):
    """Configuration for the identity module."""

    # Hard cap on a session's life, however active it is.
    session_ttl_hours: int = 168
    # Sign out a session unused for this many hours; 0 disables the idle limit.
    # It is checked against last_seen_at, which moves at most once a minute, so
    # any whole hour is accurate. The TTL above still applies on top.
    session_idle_hours: int = Field(default=0, ge=0)
    cookie_name: str = "menagerist_session"
    csrf_cookie_name: str = "menagerist_csrf"
    # None means "Secure when the request is HTTPS".
    cookie_secure: bool | None = None
    password_hasher: str = "scrypt"
    # Failed password checks allowed in one window before a key is locked.
    sign_in_username_attempts: int = Field(default=5, ge=1)
    sign_in_ip_attempts: int = Field(default=20, ge=1)
    sign_in_window_minutes: int = Field(default=15, ge=1)
    # Password hashes (about 32 MiB each) allowed to run at once in this process.
    password_hash_concurrency: int = Field(default=2, ge=1)


@lru_cache(maxsize=1)
def get_identity_settings() -> IdentitySettings:
    """Return the cached identity settings."""
    return IdentitySettings()
