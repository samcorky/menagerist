"""Naming devices: owner and admin rename, and reusing a stale device's name."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.application.adopt_device_name import (
    AdoptDeviceName,
    AdoptDeviceNameCommand,
)
from app.modules.identity.application.list_device_name_suggestions import (
    STALE_AFTER,
    ListDeviceNameSuggestions,
    ListDeviceNameSuggestionsQuery,
)
from app.modules.identity.application.rename_device import (
    RenameDevice,
    RenameDeviceCommand,
)
from app.modules.identity.application.rename_own_device import (
    RenameOwnDevice,
    RenameOwnDeviceCommand,
)
from app.modules.identity.domain.device import MAX_DEVICE_NAME_LENGTH, Device
from app.modules.identity.domain.errors import (
    DeviceNotFoundError,
    InvalidDeviceNameError,
)
from app.modules.identity.domain.session import DisplayMode, Session
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
TTL = timedelta(days=365)
SESSION_TTL = timedelta(hours=24)

FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"
OLD_FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
CHROME = " ".join(
    [
        "Mozilla/5.0 (X11; Linux x86_64)",
        "AppleWebKit/537.36 (KHTML, like Gecko)",
        "Chrome/129.0.0.0 Safari/537.36",
    ]
)


def _member(user_id: uuid.UUID) -> Actor:
    return Actor(id=user_id, roles=frozenset({Role.MEMBER.value}))


def _admin() -> Actor:
    return Actor(id=uuid.uuid7(), roles=frozenset({Role.ADMIN.value}))


def _repos(world: World) -> IdentityRepos:
    return IdentityRepos(
        users=world.users,
        sessions=world.sessions,
        attempts=world.attempts,
        tokens=world.tokens,
        devices=world.devices,
    )


async def _device(
    world: World,
    owner: uuid.UUID,
    *,
    agent: str = FIREFOX,
    platform: str = "Linux",
    mobile: bool = False,
    name: str | None = None,
    seen: timedelta = timedelta(days=30),
    display_mode: DisplayMode | None = None,
) -> Device:
    """Remember a browser last seen `seen` before NOW."""
    device = Device.create(
        user_id=owner,
        token_hash=f"hash-{uuid.uuid7()}",
        now=NOW - seen,
        ttl=TTL,
        user_agent=agent,
        platform=platform,
        mobile=mobile,
        display_mode=display_mode,
    )
    device.name = name
    await world.devices.add(device)
    return device


async def _session(
    world: World, device: Device, *, active: timedelta = timedelta(days=30)
) -> Session:
    """Start a session on `device`, last active `active` before NOW."""
    session = Session.create(
        user_id=device.user_id,
        token_hash=f"session-{uuid.uuid7()}",
        now=NOW - active,
        ttl=active + SESSION_TTL,
        device_id=device.id,
    )
    await world.sessions.add(session)
    return session


# --- Owner rename -------------------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_owner_names_changes_and_clears_a_device(
    world: World, make_user: MakeUser
) -> None:
    """The owner can set, change and clear their own device's name."""
    alice = make_user("alice")
    await world.users.add(alice)
    device = await _device(world, alice.id)
    handler = RenameOwnDevice(world.uow, get_access_guard())

    named = await handler.handle(
        RenameOwnDeviceCommand(device_id=device.id, name="  Sam's phone "),
        _member(alice.id),
    )
    assert named.name == "Sam's phone"
    assert (await world.devices.get(device.id)).name == "Sam's phone"  # type: ignore[union-attr]

    await handler.handle(
        RenameOwnDeviceCommand(device_id=device.id, name="Work laptop"),
        _member(alice.id),
    )
    assert (await world.devices.get(device.id)).name == "Work laptop"  # type: ignore[union-attr]

    await handler.handle(
        RenameOwnDeviceCommand(device_id=device.id, name=None), _member(alice.id)
    )
    assert (await world.devices.get(device.id)).name is None  # type: ignore[union-attr]


@time_machine.travel(NOW, tick=False)
async def test_owner_cannot_name_someone_elses_or_an_unknown_device(
    world: World, make_user: MakeUser
) -> None:
    """Another user's device is reported as not found, like an unknown one."""
    alice = make_user("alice")
    bob = make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)
    bobs = await _device(world, bob.id, name="Bob's")
    handler = RenameOwnDevice(world.uow, get_access_guard())

    with pytest.raises(DeviceNotFoundError):
        await handler.handle(
            RenameOwnDeviceCommand(device_id=bobs.id, name="Mine now"),
            _member(alice.id),
        )
    with pytest.raises(DeviceNotFoundError):
        await handler.handle(
            RenameOwnDeviceCommand(device_id=uuid.uuid7(), name="Nothing"),
            _member(alice.id),
        )

    assert (await world.devices.get(bobs.id)).name == "Bob's"  # type: ignore[union-attr]


@time_machine.travel(NOW, tick=False)
async def test_owner_rename_refuses_a_name_that_is_too_long(
    world: World, make_user: MakeUser
) -> None:
    """A too-long name is a validation error and changes nothing."""
    alice = make_user("alice")
    await world.users.add(alice)
    device = await _device(world, alice.id, name="Keep")
    handler = RenameOwnDevice(world.uow, get_access_guard())

    with pytest.raises(InvalidDeviceNameError):
        await handler.handle(
            RenameOwnDeviceCommand(
                device_id=device.id, name="x" * (MAX_DEVICE_NAME_LENGTH + 1)
            ),
            _member(alice.id),
        )

    assert (await world.devices.get(device.id)).name == "Keep"  # type: ignore[union-attr]


# --- Admin rename -------------------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_administrator_renames_and_clears_any_users_device(
    world: World, make_user: MakeUser
) -> None:
    """An administrator can tidy or clear a name on someone else's device."""
    alice = make_user("alice")
    await world.users.add(alice)
    device = await _device(world, alice.id, name="old name")
    handler = RenameDevice(world.uow, get_access_guard())

    renamed = await handler.handle(
        RenameDeviceCommand(device_id=device.id, name="Alice's phone"), _admin()
    )
    assert renamed.name == "Alice's phone"

    await handler.handle(RenameDeviceCommand(device_id=device.id, name=""), _admin())
    assert (await world.devices.get(device.id)).name is None  # type: ignore[union-attr]


@time_machine.travel(NOW, tick=False)
async def test_ordinary_users_cannot_rename_other_peoples_devices(
    world: World, make_user: MakeUser
) -> None:
    """Members lack the permission, even over their own devices."""
    alice = make_user("alice")
    bob = make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)
    bobs = await _device(world, bob.id, name="Bob's")
    handler = RenameDevice(world.uow, get_access_guard())

    with pytest.raises(ForbiddenError):
        await handler.handle(
            RenameDeviceCommand(device_id=bobs.id, name="Hijacked"), _member(alice.id)
        )

    assert (await world.devices.get(bobs.id)).name == "Bob's"  # type: ignore[union-attr]


@time_machine.travel(NOW, tick=False)
async def test_administrator_rename_of_an_unknown_device_is_not_found(
    world: World,
) -> None:
    """There is no device to rename."""
    handler = RenameDevice(world.uow, get_access_guard())

    with pytest.raises(DeviceNotFoundError):
        await handler.handle(
            RenameDeviceCommand(device_id=uuid.uuid7(), name="x"), _admin()
        )


@time_machine.travel(NOW, tick=False)
async def test_administrator_rename_refuses_a_name_that_is_too_long(
    world: World, make_user: MakeUser
) -> None:
    """The same length limit applies as for the owner."""
    alice = make_user("alice")
    await world.users.add(alice)
    device = await _device(world, alice.id)
    handler = RenameDevice(world.uow, get_access_guard())

    with pytest.raises(InvalidDeviceNameError):
        await handler.handle(
            RenameDeviceCommand(
                device_id=device.id, name="x" * (MAX_DEVICE_NAME_LENGTH + 1)
            ),
            _admin(),
        )


# --- Suggestions --------------------------------------------------------------


async def _suggest(world: World, alice_id: uuid.UUID, current: Session) -> list[Device]:
    handler = ListDeviceNameSuggestions(_repos(world), get_access_guard())
    return await handler.handle(
        ListDeviceNameSuggestionsQuery(current_session_id=current.id),
        _member(alice_id),
    )


@time_machine.travel(NOW, tick=False)
async def test_suggests_named_stale_devices_of_the_same_kind_of_browser(
    world: World, make_user: MakeUser
) -> None:
    """A new browser is offered the name of an older, matching, unused device."""
    alice = make_user("alice")
    await world.users.add(alice)
    stale = await _device(world, alice.id, agent=OLD_FIREFOX, name="Desk laptop")
    current = await _device(world, alice.id, seen=timedelta())
    current_session = await _session(world, current, active=timedelta())

    assert [d.id for d in await _suggest(world, alice.id, current_session)] == [
        stale.id
    ]


@time_machine.travel(NOW, tick=False)
async def test_never_suggests_a_device_that_does_not_match(
    world: World, make_user: MakeUser
) -> None:
    """Another family, platform or mobile flag is never offered."""
    alice = make_user("alice")
    await world.users.add(alice)
    await _device(world, alice.id, agent=CHROME, name="Chrome laptop")
    await _device(world, alice.id, platform="Windows", name="Windows laptop")
    await _device(world, alice.id, mobile=True, name="Phone")
    await _device(
        world, alice.id, name="Installed app", display_mode=DisplayMode.STANDALONE
    )
    current = await _device(world, alice.id, seen=timedelta())
    current_session = await _session(world, current, active=timedelta())

    assert await _suggest(world, alice.id, current_session) == []


@time_machine.travel(NOW, tick=False)
async def test_the_installed_app_is_not_offered_a_browser_tabs_name(
    world: World, make_user: MakeUser
) -> None:
    """The installed app and the same browser in a tab are different kinds."""
    alice = make_user("alice")
    await world.users.add(alice)
    await _device(world, alice.id, name="Desk laptop", display_mode=DisplayMode.BROWSER)
    current = await _device(
        world,
        alice.id,
        seen=timedelta(),
        display_mode=DisplayMode.STANDALONE,
    )
    current_session = await _session(world, current, active=timedelta())

    assert await _suggest(world, alice.id, current_session) == []


@time_machine.travel(NOW, tick=False)
async def test_does_not_suggest_unnamed_recent_or_other_users_devices(
    world: World, make_user: MakeUser
) -> None:
    """Only the user's own named devices not seen recently are offered."""
    alice = make_user("alice")
    bob = make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)
    await _device(world, alice.id, name=None)
    await _device(world, bob.id, name="Bob's laptop")
    await _device(world, alice.id, name="Used just now", seen=STALE_AFTER / 2)
    current = await _device(world, alice.id, seen=timedelta())
    current_session = await _session(world, current, active=timedelta())

    assert await _suggest(world, alice.id, current_session) == []


@time_machine.travel(NOW, tick=False)
async def test_a_device_with_recent_session_activity_is_not_stale(
    world: World, make_user: MakeUser
) -> None:
    """Activity on the device's sessions counts as seen, not just its sign-in."""
    alice = make_user("alice")
    await world.users.add(alice)
    busy = await _device(world, alice.id, name="Busy laptop")
    await _session(world, busy, active=STALE_AFTER / 2)
    current = await _device(world, alice.id, seen=timedelta())
    current_session = await _session(world, current, active=timedelta())

    assert await _suggest(world, alice.id, current_session) == []


@time_machine.travel(NOW, tick=False)
async def test_a_session_from_before_devices_does_not_affect_suggestions(
    world: World, make_user: MakeUser
) -> None:
    """A session with no device is ignored when working out which devices are idle."""
    alice = make_user("alice")
    await world.users.add(alice)
    stale = await _device(world, alice.id, agent=OLD_FIREFOX, name="Desk laptop")
    legacy = Session.create(
        user_id=alice.id, token_hash="legacy", now=NOW, ttl=SESSION_TTL
    )
    await world.sessions.add(legacy)
    current = await _device(world, alice.id, seen=timedelta())
    current_session = await _session(world, current, active=timedelta())

    assert [d.id for d in await _suggest(world, alice.id, current_session)] == [
        stale.id
    ]


@time_machine.travel(NOW, tick=False)
async def test_offers_nothing_when_the_current_device_is_already_named(
    world: World, make_user: MakeUser
) -> None:
    """A named device has no use for another name; and none without a device."""
    alice = make_user("alice")
    await world.users.add(alice)
    await _device(world, alice.id, name="Desk laptop")
    named = await _device(world, alice.id, name="Mine", seen=timedelta())
    named_session = await _session(world, named, active=timedelta())
    bare = Session.create(user_id=alice.id, token_hash="bare", now=NOW, ttl=SESSION_TTL)
    await world.sessions.add(bare)

    assert await _suggest(world, alice.id, named_session) == []
    assert await _suggest(world, alice.id, bare) == []


@time_machine.travel(NOW, tick=False)
async def test_offers_nothing_for_an_unknown_session(
    world: World, make_user: MakeUser
) -> None:
    """A session that is not found suggests nothing rather than failing."""
    alice = make_user("alice")
    await world.users.add(alice)
    handler = ListDeviceNameSuggestions(_repos(world), get_access_guard())

    result = await handler.handle(
        ListDeviceNameSuggestionsQuery(current_session_id=uuid.uuid7()),
        _member(alice.id),
    )

    assert result == []


# --- Adopting a name ----------------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_adopting_moves_the_name_and_removes_the_stale_device(
    world: World, make_user: MakeUser
) -> None:
    """The new device takes the name; the stale row and its sessions go."""
    alice = make_user("alice")
    await world.users.add(alice)
    stale = await _device(world, alice.id, agent=OLD_FIREFOX, name="Desk laptop")
    stale_session = await _session(world, stale)
    current = await _device(world, alice.id, seen=timedelta())
    current_session = await _session(world, current, active=timedelta())
    handler = AdoptDeviceName(world.uow, get_access_guard())

    adopted = await handler.handle(
        AdoptDeviceNameCommand(
            current_session_id=current_session.id, from_device_id=stale.id
        ),
        _member(alice.id),
    )

    assert adopted.id == current.id
    assert adopted.name == "Desk laptop"
    assert (await world.devices.get(current.id)).name == "Desk laptop"  # type: ignore[union-attr]
    assert await world.devices.get(stale.id) is None
    assert await world.sessions.get(stale_session.id) is None
    assert await world.sessions.get(current_session.id) is not None


@time_machine.travel(NOW, tick=False)
async def test_adopting_refuses_anything_that_was_not_suggested(
    world: World, make_user: MakeUser
) -> None:
    """Only a listed suggestion can be adopted, so nothing else is removed."""
    alice = make_user("alice")
    bob = make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)
    other_browser = await _device(world, alice.id, agent=CHROME, name="Chrome")
    recent = await _device(world, alice.id, name="Recent", seen=STALE_AFTER / 2)
    theirs = await _device(world, bob.id, name="Bob's")
    current = await _device(world, alice.id, seen=timedelta())
    current_session = await _session(world, current, active=timedelta())
    handler = AdoptDeviceName(world.uow, get_access_guard())

    for target in (other_browser, recent, theirs, current):
        with pytest.raises(DeviceNotFoundError):
            await handler.handle(
                AdoptDeviceNameCommand(
                    current_session_id=current_session.id, from_device_id=target.id
                ),
                _member(alice.id),
            )
        assert await world.devices.get(target.id) is not None
    with pytest.raises(DeviceNotFoundError):
        await handler.handle(
            AdoptDeviceNameCommand(
                current_session_id=current_session.id, from_device_id=uuid.uuid7()
            ),
            _member(alice.id),
        )
    assert (await world.devices.get(current.id)).name is None  # type: ignore[union-attr]
