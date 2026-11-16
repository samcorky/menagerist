import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.domain.device import Device
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

# A device used more recently than this is still in use, so its name is not
# offered to another browser; adopting a name removes the device it came from.
STALE_AFTER = timedelta(minutes=10)


@dataclass(kw_only=True, frozen=True)
class DeviceNameSuggestions:
    """The browser making a request and the older devices whose names it may take."""

    current: Device | None
    candidates: list[Device]


async def find_name_suggestions(
    repos: IdentityRepos, *, session_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> DeviceNameSuggestions:
    """Find the unused, named devices of the same kind of browser as `session_id`'s.

    Nothing is suggested unless the session is the user's own, belongs to a
    remembered device, and that device is still unnamed. A candidate is the
    user's, named, not the current device, of the same browser family, platform
    and mobile flag, and neither it nor its sessions were seen within
    `STALE_AFTER`. The most recently seen comes first.
    """
    session = await repos.sessions.get(session_id)
    if session is None or session.user_id != user_id or session.device_id is None:
        return DeviceNameSuggestions(current=None, candidates=[])
    current = await repos.devices.get(session.device_id)
    if current is None or current.name is not None:
        return DeviceNameSuggestions(current=current, candidates=[])

    activity: dict[uuid.UUID, datetime] = {}
    for other in await repos.sessions.list_for_user(user_id, now=now):
        if other.device_id is not None:
            activity[other.device_id] = max(
                activity.get(other.device_id, other.last_seen_at), other.last_seen_at
            )

    def last_seen(device: Device) -> datetime:
        return max(device.last_seen_at, activity.get(device.id, device.last_seen_at))

    candidates = [
        d
        for d in await repos.devices.list_for_user(user_id)
        if d.id != current.id
        and d.name is not None
        and current.is_same_kind_of_browser(d)
        and now - last_seen(d) > STALE_AFTER
    ]
    candidates.sort(key=last_seen, reverse=True)
    return DeviceNameSuggestions(current=current, candidates=candidates)


@dataclass(kw_only=True, frozen=True)
class ListDeviceNameSuggestionsQuery:
    """Request for names the current browser could take from older devices."""

    current_session_id: uuid.UUID


class ListDeviceNameSuggestions(
    QueryHandler[IdentityRepos, ListDeviceNameSuggestionsQuery, list[Device]]
):
    """Offer the calling user's older device names to a browser with none."""

    access: ClassVar[Access] = OwnAccount()

    def __init__(self, repos: IdentityRepos, guard: AccessGuard) -> None:
        super().__init__(repos, guard)

    async def _handle(
        self, query: ListDeviceNameSuggestionsQuery, actor: Actor
    ) -> list[Device]:
        """Return the devices whose names the current browser may adopt."""
        found = await find_name_suggestions(
            self._repos,
            session_id=query.current_session_id,
            user_id=actor.id,
            now=datetime.now(UTC),
        )
        return found.candidates
