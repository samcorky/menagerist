import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.domain.session import Session
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, OwnAccount
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
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


class OwnSessionSort(StrEnum):
    """What a person's sessions can be sorted by: fields of the response."""

    CREATED_AT = "created_at"
    LAST_SEEN_AT = "last_seen_at"
    EXPIRES_AT = "expires_at"


@dataclass(kw_only=True)
class ListOwnSessionsQuery(SearchedPagedQuery[OwnSessionSort]):
    """Request to list active sessions of the calling user, newest first unless told."""

    order: SortOrder = SortOrder.DESC
    current_session_id: uuid.UUID | None = None


@dataclass(kw_only=True, frozen=True)
class OwnSession:
    """An active session belonging to the user, marked if it is the current one."""

    session: Session
    current: bool = False


class ListOwnSessions(
    QueryHandler[IdentityRepos, ListOwnSessionsQuery, Page[OwnSession]]
):
    """List active sessions for the calling user, newest first."""

    access: ClassVar[Access] = OwnAccount()

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
        self, query: ListOwnSessionsQuery, actor: Actor
    ) -> Page[OwnSession]:
        """Return the actor's active sessions marked with whether they are current."""
        now = datetime.now(UTC)
        sessions = await self._repos.sessions.list_for_user(actor.id, now=now)
        own = [
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
        return page_rows(
            [e for e in own if matches_text(query.q, e.session.client_platform)],
            query.page_request(OwnSessionSort.CREATED_AT),
            id_of=lambda entry: entry.session.id,
            values={
                OwnSessionSort.CREATED_AT: lambda e: timestamp_value(
                    e.session.created_at
                ),
                OwnSessionSort.LAST_SEEN_AT: lambda e: timestamp_value(
                    e.session.last_seen_at
                ),
                OwnSessionSort.EXPIRES_AT: lambda e: timestamp_value(
                    e.session.expires_at
                ),
            },
        )
