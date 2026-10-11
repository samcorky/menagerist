from functools import lru_cache

from app.platform.config._base import MenageristBaseSettings


class IdentitySettings(MenageristBaseSettings):
    """Configuration for the identity module."""

    session_ttl_hours: int = 168
    cookie_name: str = "menagerist_session"
    csrf_cookie_name: str = "menagerist_csrf"
    # None means "Secure when the request is HTTPS".
    cookie_secure: bool | None = None
    password_hasher: str = "scrypt"


@lru_cache(maxsize=1)
def get_identity_settings() -> IdentitySettings:
    """Return the cached identity settings."""
    return IdentitySettings()
