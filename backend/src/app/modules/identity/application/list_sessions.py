import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.session_listing import SessionListing
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.authorization import AuthorizationPort  # noqa: TC001
from app.shared_kernel.cqrs import AuthorisedQueryHandler

if TYPE_CHECKING:
    from app.modules.identity.domain.user import User
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True, frozen=True)
class ListSessionsQuery:
    """Request to list active sessions, optionally filtered by user."""

    user_id: uuid.UUID | None = None


class ListSessions(
    AuthorisedQueryHandler[
        IdentityRepos, ListSessionsQuery, list[SessionListing], IdentityPermission
    ]
):
    """List active sessions for all users or a specific user, for administrators."""

    required_permission = IdentityPermission.LIST_SESSIONS

    def __init__(
        self,
        repos: IdentityRepos,
        authorization: AuthorizationPort,
        *,
        idle_timeout: timedelta | None = None,
    ) -> None:
        super().__init__(repos, authorization)
        self._idle_timeout = idle_timeout

    async def _handle(
        self, query: ListSessionsQuery, actor: Actor
    ) -> list[SessionListing]:
        """Return active sessions joined with user details, newest first.

        Raises:
            ForbiddenError: If `actor` lacks `identity:session:list`.
        """
        now = datetime.now(UTC)
        sessions = await self._repos.sessions.list_active(
            now=now, user_id=query.user_id
        )
        active_sessions = [
            s for s in sessions if not s.is_idle(now, self._idle_timeout)
        ]
        if not active_sessions:
            return []

        users_by_id: dict[uuid.UUID, User] = {}
        for s in active_sessions:
            if s.user_id not in users_by_id:
                user = await self._repos.users.get(s.user_id)
                if user is not None:
                    users_by_id[s.user_id] = user

        return [
            SessionListing(
                session=s,
                username=users_by_id[s.user_id].username,
                display_name=users_by_id[s.user_id].display_name,
            )
            for s in active_sessions
            if s.user_id in users_by_id
        ]
