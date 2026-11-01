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

    async def get(self, session_id: uuid.UUID) -> Session | None:
        """Return the session with `session_id`, or `None`."""
        ...

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        """Return the session with `token_hash`, or `None`."""
        ...

    async def list_for_user(
        self, user_id: uuid.UUID, *, now: datetime
    ) -> list[Session]:
        """Return non-expired sessions for `user_id`, newest `last_seen_at` first."""
        ...

    async def list_active(
        self, *, now: datetime, user_id: uuid.UUID | None = None
    ) -> list[Session]:
        """Return non-expired sessions, newest `last_seen_at` first."""
        ...

    async def delete(self, session_id: uuid.UUID) -> None:
        """Remove one session; unknown ids are ignored."""
        ...

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Remove every session belonging to `user_id`, returning how many went."""
        ...

    async def delete_all_except(self, user_id: uuid.UUID, keep_id: uuid.UUID) -> int:
        """Remove sessions for `user_id` except `keep_id`, returning count."""
        ...

    async def delete_expired(self, now: datetime) -> int:
        """Remove sessions expired at `now`, returning how many went."""
        ...
