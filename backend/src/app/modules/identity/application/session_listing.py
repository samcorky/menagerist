from dataclasses import dataclass

from app.modules.identity.domain.session import Session


@dataclass(kw_only=True, frozen=True)
class SessionListing:
    """An active session with its owner's identity details."""

    session: Session
    username: str
    display_name: str | None = None
