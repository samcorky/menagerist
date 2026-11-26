import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.list_own_sessions import OwnSession
from app.modules.identity.domain.device import Device
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


class OwnDeviceSort(StrEnum):
    """What a person's devices can be sorted by: fields of the response."""

    NAME = "name"
    FIRST_SEEN_AT = "first_seen_at"
    LAST_SEEN_AT = "last_seen_at"


@dataclass(kw_only=True)
class ListOwnDevicesQuery(SearchedPagedQuery[OwnDeviceSort]):
    """Request to list the calling user's signed-in devices, latest use first."""

    order: SortOrder = SortOrder.DESC
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

    @property
    def id(self) -> uuid.UUID:
        """The device's id, or that of its only session when it is not remembered."""
        return self.device.id if self.device else self.sessions[0].session.id

    @property
    def first_seen_at(self) -> datetime:
        """When the device was first seen, or its session started if not remembered."""
        return (
            self.device.created_at
            if self.device
            else self.sessions[0].session.created_at
        )

    @property
    def last_seen_at(self) -> datetime:
        """When the device was last seen (a session's last use if not remembered)."""
        return (
            self.device.last_seen_at
            if self.device
            else self.sessions[0].session.last_seen_at
        )


class ListOwnDevices(QueryHandler[IdentityRepos, ListOwnDevicesQuery, Page[OwnDevice]]):
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
    ) -> Page[OwnDevice]:
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
        entries = [
            OwnDevice(device=None, sessions=[entry])
            if isinstance(entry, OwnSession)
            else OwnDevice(device=devices[entry], sessions=groups[entry])
            for entry in order
        ]
        return page_rows(
            [
                entry
                for entry in entries
                if matches_text(
                    query.q,
                    entry.device.name if entry.device else None,
                    entry.device.platform if entry.device else None,
                )
            ],
            query.page_request(OwnDeviceSort.LAST_SEEN_AT),
            id_of=lambda entry: entry.id,
            values={
                OwnDeviceSort.NAME: lambda entry: (
                    entry.device.name.lower()
                    if entry.device and entry.device.name
                    else None
                ),
                OwnDeviceSort.FIRST_SEEN_AT: lambda entry: timestamp_value(
                    entry.first_seen_at
                ),
                OwnDeviceSort.LAST_SEEN_AT: lambda entry: timestamp_value(
                    entry.last_seen_at
                ),
            },
        )
