import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.identity.domain.session import Session
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True, frozen=True)
class ListOwnSessionsQuery:
    """Request to list active sessions of the calling user."""

    current_session_id: uuid.UUID | None = None


@dataclass(kw_only=True, frozen=True)
class OwnSession:
    """An active session belonging to the user, marked if it is the current one."""

    session: Session
    current: bool = False


class ListOwnSessions(
    QueryHandler[IdentityRepos, ListOwnSessionsQuery, list[OwnSession]]
):
    """List active sessions for the calling user, newest first."""

    def __init__(
        self,
        repos: IdentityRepos,
        *,
        idle_timeout: timedelta | None = None,
    ) -> None:
        super().__init__(repos)
        self._idle_timeout = idle_timeout

    async def handle(
        self, query: ListOwnSessionsQuery, actor: Actor
    ) -> list[OwnSession]:
        """Return the actor's active sessions marked with whether they are current."""
        now = datetime.now(UTC)
        sessions = await self._repos.sessions.list_for_user(actor.id, now=now)
        return [
            OwnSession(
                session=s,
                current=(
                    query.current_session_id is not None
                    and s.id == query.current_session_id
                ),
            )
            for s in sessions
            if not s.is_idle(now, self._idle_timeout)
        ]
