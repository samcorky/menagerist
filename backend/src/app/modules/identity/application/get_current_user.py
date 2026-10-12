import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.identity.domain.user import User
from app.modules.identity.ports.session_token_generator import (  # noqa: TC001
    SessionTokenGenerator,
)
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

LAST_SEEN_INTERVAL = timedelta(minutes=1)


@dataclass(kw_only=True)
class GetCurrentUserQuery:
    """Request to resolve a session token to its user."""

    token: str

    def __repr__(self) -> str:
        """Keep the token out of logs and tracebacks."""
        return "GetCurrentUserQuery()"


@dataclass(kw_only=True, frozen=True)
class ResolvedSession:
    """A live session's user and its row id (not a secret; it cannot authenticate)."""

    user: User
    session_id: uuid.UUID


class GetCurrentUser(
    CommandHandler[IdentityUnitOfWork, GetCurrentUserQuery, ResolvedSession | None]
):
    """Resolve a session token to its user.

    A command handler because it records activity: `last_seen_at` moves at most
    once a minute, so most calls write nothing.
    """

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        tokens: SessionTokenGenerator,
        *,
        idle_timeout: timedelta | None = None,
    ) -> None:
        super().__init__(uow)
        self._tokens = tokens
        self._idle_timeout = idle_timeout

    async def handle(
        self, query: GetCurrentUserQuery, actor: Actor
    ) -> ResolvedSession | None:
        """Return the user and session id, or `None` if there is no usable session.

        A session is unusable when unknown, expired, idle for longer than the
        idle timeout (checked against `last_seen_at`, which moves at most once a
        minute) or owned by a disabled user. Expired and idle sessions are removed.
        """
        now = datetime.now(UTC)
        async with self._uow as repos:
            session = await repos.sessions.get_by_token_hash(
                self._tokens.token_hash(query.token)
            )
            if session is None:
                return None
            if session.is_expired(now) or session.is_idle(now, self._idle_timeout):
                await repos.sessions.delete(session.id)
                await self._uow.commit()
                return None
            user = await repos.users.get(session.user_id)
            if user is None or user.disabled:
                return None
            if now - session.last_seen_at >= LAST_SEEN_INTERVAL:
                session.seen(now)
                await repos.sessions.save(session)
                await self._uow.commit()
            return ResolvedSession(user=user, session_id=session.id)
