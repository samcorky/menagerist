from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.identity.domain.session import Session


class SessionRepository(Protocol):
    """Access to sign-in sessions, independent of storage backend."""

    async def add(self, session: Session) -> None:
        """Add a new session."""
        ...

    async def save(self, session: Session) -> None:
        """Persist changes to an existing session (e.g. `last_seen_at`)."""
        ...

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        """Return the session with `token_hash`, or `None`."""
        ...

    async def delete(self, session_id: uuid.UUID) -> None:
        """Remove one session; unknown ids are ignored."""
        ...

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Remove every session belonging to `user_id`, returning how many went."""
        ...

    async def delete_expired(self, now: datetime) -> int:
        """Remove sessions expired at `now`, returning how many went."""
        ...
