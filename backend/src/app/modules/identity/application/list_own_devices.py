import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.list_own_sessions import OwnSession
from app.modules.identity.domain.device import Device
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True, frozen=True)
class ListOwnDevicesQuery:
    """Request to list the calling user's signed-in devices."""

    current_session_id: uuid.UUID | None = None


@dataclass(kw_only=True, frozen=True)
class OwnDevice:
    """A browser the user is signed in on, with its active sessions.

    `device` is `None` for a session started before devices were remembered;
    such a session is listed on its own.
    """

    device: Device | None
    sessions: list[OwnSession]

    @property
    def current(self) -> bool:
        """Whether the current session belongs to this device."""
        return any(s.current for s in self.sessions)


class ListOwnDevices(QueryHandler[IdentityRepos, ListOwnDevicesQuery, list[OwnDevice]]):
    """List the calling user's active sessions grouped by device, newest first."""

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
        self, query: ListOwnDevicesQuery, actor: Actor
    ) -> list[OwnDevice]:
        """Return one entry per device with active sessions, plus ungrouped sessions.

        A remembered device with no active session is signed out and not listed.
        """
        now = datetime.now(UTC)
        sessions = await self._repos.sessions.list_for_user(actor.id, now=now)
        devices = {d.id: d for d in await self._repos.devices.list_for_user(actor.id)}
        # Sessions arrive newest first, so each group takes its first one's place.
        groups: dict[uuid.UUID, list[OwnSession]] = {}
        order: list[uuid.UUID | OwnSession] = []
        for session in sessions:
            if session.is_idle(now, self._idle_timeout):
                continue
            own = OwnSession(
                session=session,
                current=session.id == query.current_session_id,
            )
            if session.device_id is None or session.device_id not in devices:
                order.append(own)
            elif session.device_id in groups:
                groups[session.device_id].append(own)
            else:
                groups[session.device_id] = [own]
                order.append(session.device_id)
        return [
            OwnDevice(device=None, sessions=[entry])
            if isinstance(entry, OwnSession)
            else OwnDevice(device=devices[entry], sessions=groups[entry])
            for entry in order
        ]
