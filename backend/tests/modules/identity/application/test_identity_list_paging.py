"""Sorting and paging of the identity lists: every key, both ways, to the end."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.application.list_own_api_tokens import (
    ApiTokenSort,
    ListOwnApiTokensQuery,
)
from app.modules.identity.application.list_own_devices import (
    ListOwnDevices,
    ListOwnDevicesQuery,
    OwnDeviceSort,
)
from app.modules.identity.application.list_own_sessions import (
    ListOwnSessions,
    ListOwnSessionsQuery,
    OwnSessionSort,
)
from app.modules.identity.application.list_sessions import (
    ListSessions,
    ListSessionsQuery,
    SessionSort,
)
from app.modules.identity.application.list_users import ListUsersQuery, UserSort
from app.modules.identity.domain.device import Device
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.paging import SortOrder

if TYPE_CHECKING:
    import uuid

    from tests.modules.identity.application.conftest import ActorFor, Cases, IssueToken
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
TTL = timedelta(hours=24)


def _repos(world: World) -> IdentityRepos:
    return IdentityRepos(
        users=world.users,
        sessions=world.sessions,
        attempts=world.attempts,
        tokens=world.tokens,
        devices=world.devices,
    )


@time_machine.travel(NOW, tick=False)
@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", list(ApiTokenSort))
async def test_tokens_page_through_every_sort_key(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
    sort: ApiTokenSort,
    order: SortOrder,
) -> None:
    """Following `next` visits each token once, whatever the key and direction."""
    alice = make_user("alice")
    await world.users.add(alice)
    for name in ["b", "A", "c"]:
        await issue_token(alice, name=name, days=30)

    seen: list[uuid.UUID] = []
    request = ListOwnApiTokensQuery(limit=2, sort=sort, order=order)
    while True:
        page = await cases.list_own_api_tokens.handle(request, actor_for(alice))
        assert page.total == 3
        seen.extend(t.id for t in page.items)
        if page.next is None:
            break
        request = ListOwnApiTokensQuery(
            after=page.next, limit=2, sort=sort, order=order
        )

    assert len(seen) == len(set(seen)) == 3


@time_machine.travel(NOW, tick=False)
@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", list(OwnSessionSort))
async def test_own_sessions_page_through_every_sort_key(
    world: World, make_user: MakeUser, sort: OwnSessionSort, order: SortOrder
) -> None:
    """Following `next` visits each of the person's sessions once."""
    alice = make_user("alice")
    await world.users.add(alice)
    for n in range(3):
        await world.sessions.add(
            Session.create(
                user_id=alice.id,
                token_hash=f"hash-{n}",
                now=NOW - timedelta(hours=n),
                ttl=TTL,
            )
        )
    handler = ListOwnSessions(_repos(world), get_access_guard())
    actor = Actor(id=alice.id, roles=frozenset({"member"}))

    seen: list[uuid.UUID] = []
    request = ListOwnSessionsQuery(limit=2, sort=sort, order=order)
    while True:
        page = await handler.handle(request, actor)
        seen.extend(entry.session.id for entry in page.items)
        if page.next is None:
            break
        request = ListOwnSessionsQuery(after=page.next, limit=2, sort=sort, order=order)

    assert len(seen) == len(set(seen)) == 3


@time_machine.travel(NOW, tick=False)
@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", list(OwnDeviceSort))
async def test_own_devices_page_through_every_sort_key(
    world: World, make_user: MakeUser, sort: OwnDeviceSort, order: SortOrder
) -> None:
    """Following `next` visits each device once, and a session with no device too."""
    alice = make_user("alice")
    await world.users.add(alice)
    for n, name in enumerate(["Laptop", None]):
        device = Device.create(
            user_id=alice.id,
            token_hash=f"device-{n}",
            now=NOW - timedelta(hours=n),
            ttl=TTL,
        )
        device.name = name
        await world.devices.add(device)
        await world.sessions.add(
            Session.create(
                user_id=alice.id,
                token_hash=f"session-{n}",
                now=NOW - timedelta(hours=n),
                ttl=TTL,
                device_id=device.id,
            )
        )
    await world.sessions.add(
        Session.create(user_id=alice.id, token_hash="no-device", now=NOW, ttl=TTL)
    )
    handler = ListOwnDevices(_repos(world), get_access_guard())
    actor = Actor(id=alice.id, roles=frozenset({"member"}))

    seen: list[uuid.UUID] = []
    request = ListOwnDevicesQuery(limit=2, sort=sort, order=order)
    while True:
        page = await handler.handle(request, actor)
        seen.extend(entry.id for entry in page.items)
        if page.next is None:
            break
        request = ListOwnDevicesQuery(after=page.next, limit=2, sort=sort, order=order)

    assert len(seen) == len(set(seen)) == 3


@time_machine.travel(NOW, tick=False)
@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", list(SessionSort))
async def test_admin_sessions_page_through_every_sort_key(
    world: World, make_user: MakeUser, sort: SessionSort, order: SortOrder
) -> None:
    """Following `next` visits each active session once, for every key."""
    people = [make_user(name) for name in ("alice", "bob", "carol")]
    for person in people:
        await world.users.add(person)
        await world.sessions.add(
            Session.create(
                user_id=person.id,
                token_hash=f"hash-{person.username}",
                now=NOW,
                ttl=TTL,
            )
        )
    admin = make_user("admin", role=Role.ADMIN)
    handler = ListSessions(_repos(world), get_access_guard())
    actor = Actor(id=admin.id, roles=frozenset({"admin"}))

    seen: list[uuid.UUID] = []
    request = ListSessionsQuery(limit=2, sort=sort, order=order)
    while True:
        page = await handler.handle(request, actor)
        seen.extend(item.session.id for item in page.items)
        if page.next is None:
            break
        request = ListSessionsQuery(after=page.next, limit=2, sort=sort, order=order)

    assert len(seen) == len(set(seen)) == 3


@time_machine.travel(NOW, tick=False)
@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", list(UserSort))
async def test_users_page_through_every_sort_key(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    sort: UserSort,
    order: SortOrder,
) -> None:
    """Following `next` visits each account once, whatever the key and direction."""
    admin = make_user("admin", role=Role.ADMIN)
    await world.users.add(admin)
    for name in ("bob", "alice", "carol"):
        await world.users.add(make_user(name))

    seen: list[uuid.UUID] = []
    request = ListUsersQuery(limit=2, sort=sort, order=order)
    while True:
        page = await cases.list_users.handle(request, actor_for(admin))
        assert page.total == 4
        seen.extend(item.user.id for item in page.items)
        if page.next is None:
            break
        request = ListUsersQuery(after=page.next, limit=2, sort=sort, order=order)

    assert len(seen) == len(set(seen)) == 4


@time_machine.travel(NOW, tick=False)
async def test_tokens_search_the_name(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """`q` keeps the tokens whose name contains it, and the total counts only those."""
    alice = make_user("alice")
    await world.users.add(alice)
    for name in ("Café backup", "Phone", "Backup 2"):
        await issue_token(alice, name=name, days=30)

    page = await cases.list_own_api_tokens.handle(
        ListOwnApiTokensQuery(q="BACKUP"), actor_for(alice)
    )

    assert sorted(t.name for t in page.items) == ["Backup 2", "Café backup"]
    assert page.total == 2


@time_machine.travel(NOW, tick=False)
async def test_devices_and_own_sessions_search_what_the_person_would_call_them(
    world: World, make_user: MakeUser
) -> None:
    """Devices match their name and platform; sessions their platform."""
    alice = make_user("alice")
    await world.users.add(alice)
    laptop = Device.create(
        user_id=alice.id, token_hash="laptop", now=NOW, ttl=TTL, platform="macOS"
    )
    laptop.name = "Work laptop"
    phone = Device.create(
        user_id=alice.id, token_hash="phone", now=NOW, ttl=TTL, platform="Android"
    )
    for device in (laptop, phone):
        await world.devices.add(device)
        await world.sessions.add(
            Session.create(
                user_id=alice.id,
                token_hash=f"session-{device.token_hash}",
                now=NOW,
                ttl=TTL,
                device_id=device.id,
                client_platform=device.platform,
            )
        )
    actor = Actor(id=alice.id, roles=frozenset({"member"}))

    devices = await ListOwnDevices(_repos(world), get_access_guard()).handle(
        ListOwnDevicesQuery(q="LAPTOP"), actor
    )
    by_platform = await ListOwnDevices(_repos(world), get_access_guard()).handle(
        ListOwnDevicesQuery(q="android"), actor
    )
    sessions = await ListOwnSessions(_repos(world), get_access_guard()).handle(
        ListOwnSessionsQuery(q="macos"), actor
    )

    assert [d.id for d in devices.items] == [laptop.id]
    assert [d.id for d in by_platform.items] == [phone.id]
    assert len(sessions.items) == 1


@time_machine.travel(NOW, tick=False)
async def test_admin_sessions_search_the_user_the_device_and_where_from(
    world: World, make_user: MakeUser
) -> None:
    """An administrator can find a session by who, what and where."""
    people = {name: make_user(name) for name in ("alice", "bob")}
    for person in people.values():
        await world.users.add(person)
    workstation = Device.create(
        user_id=people["alice"].id, token_hash="ws", now=NOW, ttl=TTL
    )
    workstation.name = "Workstation"
    await world.devices.add(workstation)
    await world.sessions.add(
        Session.create(
            user_id=people["alice"].id,
            token_hash="a",
            now=NOW,
            ttl=TTL,
            device_id=workstation.id,
            user_agent="Firefox on Linux",
            client_ip="192.0.2.7",
        )
    )
    await world.sessions.add(
        Session.create(
            user_id=people["bob"].id,
            token_hash="b",
            now=NOW,
            ttl=TTL,
            user_agent="Safari",
            client_ip="198.51.100.9",
        )
    )
    handler = ListSessions(_repos(world), get_access_guard())
    admin = Actor(id=people["alice"].id, roles=frozenset({"admin"}))

    async def usernames(q: str) -> list[str]:
        page = await handler.handle(ListSessionsQuery(q=q), admin)
        return [item.username for item in page.items]

    assert await usernames("BOB") == ["bob"]
    assert await usernames("firefox") == ["alice"]
    assert await usernames("198.51") == ["bob"]
    assert await usernames("WORKSTATION") == ["alice"]
    assert await usernames("zebra") == []


@time_machine.travel(NOW, tick=False)
async def test_users_search_username_display_name_and_role(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Accounts are found by username, display name or role."""
    admin = make_user("admin", role=Role.ADMIN)
    await world.users.add(admin)
    await world.users.add(make_user("alice", display_name="Álvaro Díaz"))
    await world.users.add(make_user("bob"))

    async def names(q: str) -> list[str]:
        page = await cases.list_users.handle(ListUsersQuery(q=q), actor_for(admin))
        return sorted(item.user.username for item in page.items)

    assert await names("alvaro") == ["alice"]
    assert await names("BOB") == ["bob"]
    assert await names("admin") == ["admin"]
