import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.session_listing import SessionListing
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import (
    Page,
    SearchedPagedQuery,
    SortOrder,
    page_rows,
    timestamp_value,
)
from app.shared_kernel.text import matches_text

if TYPE_CHECKING:
    from app.modules.identity.domain.user import User
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


class SessionSort(StrEnum):
    """What the active sessions can be sorted by: fields of the response."""

    USERNAME = "username"
    CREATED_AT = "created_at"
    LAST_SEEN_AT = "last_seen_at"
    EXPIRES_AT = "expires_at"


@dataclass(kw_only=True)
class ListSessionsQuery(SearchedPagedQuery[SessionSort]):
    """Request to list active sessions, newest first, optionally of one user."""

    order: SortOrder = SortOrder.DESC
    user_id: uuid.UUID | None = None


class ListSessions(
    QueryHandler[IdentityRepos, ListSessionsQuery, Page[SessionListing]]
):
    """List active sessions for all users or a specific user, for administrators."""

    access: ClassVar[Access] = Requires(IdentityPermission.LIST_SESSIONS)

    def __init__(
        self,
        repos: IdentityRepos,
        guard: AccessGuard,
        *,
        idle_timeout: timedelta | None = None,
    ) -> None:
        super().__init__(repos, guard)
        self._idle_timeout = idle_timeout

    async def _handle(
        self, query: ListSessionsQuery, actor: Actor
    ) -> Page[SessionListing]:
        """Return a page of active sessions joined with user details.

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
            return Page(items=[], total=0)

        users_by_id: dict[uuid.UUID, User] = {}
        for s in active_sessions:
            if s.user_id not in users_by_id:
                user = await self._repos.users.get(s.user_id)
                if user is not None:
                    users_by_id[s.user_id] = user

        device_names: dict[uuid.UUID, str | None] = {}
        for s in active_sessions:
            if s.device_id is not None and s.device_id not in device_names:
                device = await self._repos.devices.get(s.device_id)
                device_names[s.device_id] = None if device is None else device.name

        listings = [
            SessionListing(
                session=s,
                username=users_by_id[s.user_id].username,
                display_name=users_by_id[s.user_id].display_name,
                device_name=None if s.device_id is None else device_names[s.device_id],
            )
            for s in active_sessions
            if s.user_id in users_by_id
        ]
        return page_rows(
            [
                item
                for item in listings
                if matches_text(
                    query.q,
                    item.username,
                    item.display_name,
                    item.device_name,
                    item.session.user_agent,
                    item.session.client_ip,
                )
            ],
            query.page_request(SessionSort.CREATED_AT),
            id_of=lambda item: item.session.id,
            values={
                SessionSort.USERNAME: lambda item: item.username.lower(),
                SessionSort.CREATED_AT: lambda item: timestamp_value(
                    item.session.created_at
                ),
                SessionSort.LAST_SEEN_AT: lambda item: timestamp_value(
                    item.session.last_seen_at
                ),
                SessionSort.EXPIRES_AT: lambda item: timestamp_value(
                    item.session.expires_at
                ),
            },
        )
