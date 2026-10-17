from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.identity.domain.session import Session


class InMemorySessionRepository:
    """Dict-backed `SessionRepository` for tests."""

    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, Session] = {}

    async def add(self, session: Session) -> None:
        """Add a new session."""
        self._sessions[session.id] = session

    async def save(self, session: Session) -> None:
        """Persist changes to an existing session (e.g. `last_seen_at`)."""
        self._sessions[session.id] = session

    async def get(self, session_id: uuid.UUID) -> Session | None:
        """Return the session with `session_id`, or `None`."""
        return self._sessions.get(session_id)

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        """Return the session with `token_hash`, or `None`."""
        return next(
            (s for s in self._sessions.values() if s.token_hash == token_hash), None
        )

    async def list_for_user(
        self, user_id: uuid.UUID, *, now: datetime
    ) -> list[Session]:
        """Return non-expired sessions for `user_id`, newest `last_seen_at` first."""
        sessions = [
            s
            for s in self._sessions.values()
            if s.user_id == user_id and not s.is_expired(now)
        ]
        return sorted(sessions, key=lambda s: s.last_seen_at, reverse=True)

    async def list_active(
        self, *, now: datetime, user_id: uuid.UUID | None = None
    ) -> list[Session]:
        """Return non-expired sessions, newest `last_seen_at` first."""
        sessions = [
            s
            for s in self._sessions.values()
            if not s.is_expired(now) and (user_id is None or s.user_id == user_id)
        ]
        return sorted(sessions, key=lambda s: s.last_seen_at, reverse=True)

    async def delete(self, session_id: uuid.UUID) -> None:
        """Remove one session; unknown ids are ignored."""
        self._sessions.pop(session_id, None)

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Remove every session belonging to `user_id`, returning how many went."""
        kept = {i: s for i, s in self._sessions.items() if s.user_id != user_id}
        ended = len(self._sessions) - len(kept)
        self._sessions = kept
        return ended

    async def delete_all_except(self, user_id: uuid.UUID, keep_id: uuid.UUID) -> int:
        """Remove sessions for `user_id` except `keep_id`, returning count."""
        kept = {
            i: s
            for i, s in self._sessions.items()
            if s.user_id != user_id or i == keep_id
        }
        ended = len(self._sessions) - len(kept)
        self._sessions = kept
        return ended

    async def delete_expired(self, now: datetime) -> int:
        """Remove sessions expired at `now`, returning how many went."""
        expired = [i for i, s in self._sessions.items() if s.is_expired(now)]
        for session_id in expired:
            del self._sessions[session_id]
        return len(expired)
