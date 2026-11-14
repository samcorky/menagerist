"""Remembered browsers: the device cookie, its sign-in limit and its housekeeping."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.application.change_password import ChangePasswordCommand
from app.modules.identity.application.client_device import ClientDevice
from app.modules.identity.application.list_own_devices import (
    ListOwnDevices,
    ListOwnDevicesQuery,
)
from app.modules.identity.application.purge_expired_credentials import (
    PurgeExpiredCredentials,
    PurgeExpiredCredentialsCommand,
)
from app.modules.identity.application.reset_password import ResetPasswordCommand
from app.modules.identity.application.revoke_other_sessions import (
    RevokeOtherSessions,
    RevokeOtherSessionsCommand,
)
from app.modules.identity.application.revoke_own_device import (
    RevokeOwnDevice,
    RevokeOwnDeviceCommand,
)
from app.modules.identity.application.sign_in import SignInCommand
from app.modules.identity.application.sign_out import SignOutCommand
from app.modules.identity.application.update_user import UpdateUserCommand
from app.modules.identity.domain.errors import (
    CurrentSessionError,
    DeviceNotFoundError,
    InvalidCredentialsError,
    SignInThrottledError,
)
from app.modules.identity.domain.session import DisplayMode, Session
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor

if TYPE_CHECKING:
    from app.modules.identity.application.session_start import SignedInResult
    from tests.modules.identity.application.conftest import Cases
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
PASSWORD = "password-123"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _actor(user_id: uuid.UUID, role: str = "member") -> Actor:
    return Actor(id=user_id, roles=frozenset({role}))


def _repos(world: World) -> IdentityRepos:
    return IdentityRepos(
        users=world.users,
        sessions=world.sessions,
        attempts=world.attempts,
        tokens=world.tokens,
        devices=world.devices,
    )


async def _sign_in(
    cases: Cases,
    username: str = "alice",
    password: str = PASSWORD,
    *,
    device_token: str | None = None,
    device: ClientDevice | None = None,
    client_ip: str | None = None,
) -> SignedInResult:
    return await cases.sign_in.handle(
        SignInCommand(
            username=username,
            password=password,
            client_ip=client_ip,
            device=device,
            device_token=device_token,
        ),
        ANONYMOUS_ACTOR,
    )


async def _fail(cases: Cases, times: int, **kwargs: str | None) -> None:
    """Make `times` wrong-password attempts for alice, ignoring how each is refused."""
    for _ in range(times):
        with pytest.raises((InvalidCredentialsError, SignInThrottledError)):
            await _sign_in(cases, password="wrong-password", **kwargs)  # type: ignore[arg-type]


# --- remembering a browser --------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_sign_in_remembers_the_browser_storing_only_the_hash(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A first sign-in creates a device; only its cookie's hash is stored."""
    alice = make_user("alice")
    await world.users.add(alice)

    result = await _sign_in(
        cases,
        device=ClientDevice(
            user_agent="Firefox", platform="Linux", mobile=False, display_mode=None
        ),
    )

    device = await world.devices.get_by_token_hash(_hash(result.device_token))
    assert device is not None
    assert device.user_id == alice.id
    assert device.token_hash != result.device_token
    assert (device.user_agent, device.platform, device.mobile) == (
        "Firefox",
        "Linux",
        False,
    )
    assert device.created_at == device.last_seen_at == NOW
    assert device.expires_at == NOW + timedelta(days=365)
    session = await world.sessions.get(result.session_id)
    assert session is not None
    assert session.device_id == device.id


async def test_signing_in_again_keeps_the_device_and_ends_its_old_session(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """The same browser keeps its cookie; its earlier, unusable session is ended."""
    await world.users.add(make_user("alice"))
    first = await _sign_in(cases)

    with time_machine.travel(NOW + timedelta(days=3), tick=False):
        second = await _sign_in(
            cases,
            device_token=first.device_token,
            device=ClientDevice(user_agent="Firefox 2"),
        )

    assert second.device_token == first.device_token
    assert await world.sessions.get(first.session_id) is None
    device = await world.devices.get_by_token_hash(_hash(first.device_token))
    assert device is not None
    assert device.user_agent == "Firefox 2"
    assert device.last_seen_at == NOW + timedelta(days=3)
    assert device.expires_at == NOW + timedelta(days=368)


async def test_display_mode_is_recorded_on_the_session(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """The display mode the app reported is kept with the session it started."""
    await world.users.add(make_user("alice"))

    result = await _sign_in(
        cases, device=ClientDevice(display_mode=DisplayMode.STANDALONE)
    )

    session = await world.sessions.get(result.session_id)
    assert session is not None
    assert session.display_mode is DisplayMode.STANDALONE


async def test_another_accounts_cookie_is_replaced(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A browser shared by two people gets a new device for the second account."""
    await world.users.add(make_user("alice"))
    await world.users.add(make_user("bob"))
    alices = await _sign_in(cases, "alice")

    bobs = await _sign_in(cases, "bob", device_token=alices.device_token)

    assert bobs.device_token != alices.device_token
    assert await world.devices.get_by_token_hash(_hash(alices.device_token))


async def test_an_expired_device_is_replaced(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A device past its lifetime is not reused and gets no higher limit."""
    await world.users.add(make_user("alice"))
    first = await _sign_in(cases)

    with time_machine.travel(datetime.now(UTC) + timedelta(days=366), tick=False):
        second = await _sign_in(cases, device_token=first.device_token)

    assert second.device_token != first.device_token


async def test_signing_out_keeps_the_device(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Signing out ends the session but does not forget the browser."""
    await world.users.add(make_user("alice"))
    result = await _sign_in(cases)

    await cases.sign_out.handle(SignOutCommand(token=result.token), ANONYMOUS_ACTOR)

    assert await world.sessions.get(result.session_id) is None
    assert await world.devices.get_by_token_hash(_hash(result.device_token))


# --- the device's own sign-in limit -------------------------------------------


async def test_a_remembered_browser_signs_in_while_the_username_is_locked(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Failures from elsewhere lock the username but not the browser with the cookie."""
    await world.users.add(make_user("alice"))
    remembered = await _sign_in(cases)
    await _fail(cases, 30)

    with pytest.raises(SignInThrottledError):
        await _sign_in(cases)

    result = await _sign_in(cases, device_token=remembered.device_token)
    assert result.user.username == "alice"


async def test_a_remembered_browser_still_has_a_finite_limit(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A stolen cookie is not a free pass: the device locks after its own limit."""
    await world.users.add(make_user("alice"))
    remembered = await _sign_in(cases)
    limit = cases.throttle.policy.device_limit

    await _fail(cases, limit, device_token=remembered.device_token)

    with pytest.raises(SignInThrottledError):
        await _sign_in(cases, device_token=remembered.device_token)


async def test_a_cookie_does_not_help_another_username(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Alice's cookie gives no higher limit when signing in as Bob."""
    await world.users.add(make_user("alice"))
    await world.users.add(make_user("bob"))
    alices = await _sign_in(cases, "alice")
    for _ in range(cases.throttle.policy.username_limit):
        with pytest.raises(InvalidCredentialsError):
            await _sign_in(cases, "bob", "wrong-password")

    with pytest.raises(SignInThrottledError):
        await _sign_in(cases, "bob", device_token=alices.device_token)


async def test_a_cookie_for_an_unknown_username_counts_as_no_cookie(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """An unknown username is throttled the same with or without a cookie."""
    await world.users.add(make_user("alice"))
    alices = await _sign_in(cases, "alice")
    limit = cases.throttle.policy.username_limit

    for _ in range(limit):
        with pytest.raises(InvalidCredentialsError):
            await _sign_in(cases, "nobody", device_token=alices.device_token)

    with pytest.raises(SignInThrottledError):
        await _sign_in(cases, "nobody", device_token=alices.device_token)


async def test_an_unknown_cookie_counts_as_no_cookie(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A made-up cookie is counted on the username like any other attempt."""
    await world.users.add(make_user("alice"))
    await _fail(cases, cases.throttle.policy.username_limit)

    with pytest.raises(SignInThrottledError):
        await _sign_in(cases, device_token="made-up")


# --- forgetting browsers ------------------------------------------------------


async def test_changing_the_password_forgets_every_browser(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Old cookies lose their limit; the browser changing it is remembered afresh."""
    alice = make_user("alice")
    await world.users.add(alice)
    other = await _sign_in(cases)
    this = await _sign_in(cases)

    result = await cases.change_password.handle(
        ChangePasswordCommand(current_password=PASSWORD, new_password="new-password-1"),
        _actor(alice.id),
    )

    assert await world.devices.get_by_token_hash(_hash(other.device_token)) is None
    assert await world.devices.get_by_token_hash(_hash(this.device_token)) is None
    devices = await world.devices.list_for_user(alice.id)
    assert [d.token_hash for d in devices] == [_hash(result.device_token)]


async def test_resetting_the_password_forgets_every_browser(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """An administrator's reset forgets the account's browsers."""
    admin = make_user("admin", role=Role.ADMIN)
    alice = make_user("alice")
    await world.users.add(admin)
    await world.users.add(alice)
    await _sign_in(cases)

    await cases.reset_password.handle(
        ResetPasswordCommand(user_id=alice.id, password="temporary-pass-1"),
        _actor(admin.id, "admin"),
    )

    assert await world.devices.list_for_user(alice.id) == []


async def test_disabling_an_account_forgets_its_browsers(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A disabled account keeps no remembered browsers."""
    admin = make_user("admin", role=Role.ADMIN)
    alice = make_user("alice")
    await world.users.add(admin)
    await world.users.add(alice)
    await _sign_in(cases)

    await cases.update_user.handle(
        UpdateUserCommand(user_id=alice.id, disabled=True), _actor(admin.id, "admin")
    )

    assert await world.devices.list_for_user(alice.id) == []


async def test_signing_out_everywhere_else_forgets_the_other_browsers(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Only this browser and its session are kept."""
    alice = make_user("alice")
    await world.users.add(alice)
    other = await _sign_in(cases)
    this = await _sign_in(cases)

    ended = await RevokeOtherSessions(world.uow, get_access_guard()).handle(
        RevokeOtherSessionsCommand(current_session_id=this.session_id),
        _actor(alice.id),
    )

    assert ended == 1
    assert await world.devices.get_by_token_hash(_hash(other.device_token)) is None
    assert await world.devices.get_by_token_hash(_hash(this.device_token))
    assert await world.sessions.get(this.session_id)


async def test_purge_forgets_expired_browsers(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """The clean-up job removes devices past their lifetime and counts them."""
    alice = make_user("alice")
    await world.users.add(alice)
    await _sign_in(cases)

    result = await PurgeExpiredCredentials(world.uow, get_access_guard()).handle(
        PurgeExpiredCredentialsCommand(now=datetime.now(UTC) + timedelta(days=366)),
        SYSTEM_ACTOR,
    )

    assert result.devices == 1
    assert await world.devices.list_for_user(alice.id) == []


# --- the devices list ---------------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_devices_are_listed_with_their_sessions_newest_first(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """One entry per signed-in browser; older sessions without a device stand alone."""
    alice = make_user("alice")
    await world.users.add(alice)
    legacy = Session.create(
        user_id=alice.id, token_hash="legacy", now=NOW, ttl=timedelta(hours=1)
    )
    legacy.seen(NOW - timedelta(minutes=30))
    await world.sessions.add(legacy)
    first = await _sign_in(cases)
    second = await _sign_in(cases)
    with time_machine.travel(NOW + timedelta(minutes=1), tick=False):
        current = await _sign_in(cases, device_token=second.device_token)
    signed_out = await _sign_in(cases)
    await cases.sign_out.handle(SignOutCommand(token=signed_out.token), ANONYMOUS_ACTOR)

    listed = await ListOwnDevices(_repos(world), get_access_guard()).handle(
        ListOwnDevicesQuery(current_session_id=current.session_id), _actor(alice.id)
    )

    assert [(d.device is None, d.current) for d in listed] == [
        (False, True),
        (False, False),
        (True, False),
    ]
    assert [[s.session.id for s in d.sessions] for d in listed] == [
        [current.session_id],
        [first.session_id],
        [legacy.id],
    ]


@time_machine.travel(NOW, tick=False)
async def test_idle_sessions_are_left_out_of_the_devices_list(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A device whose only session is idle is not listed."""
    alice = make_user("alice")
    await world.users.add(alice)
    result = await _sign_in(cases)
    session = await world.sessions.get(result.session_id)
    assert session is not None
    session.seen(NOW - timedelta(hours=3))

    listed = await ListOwnDevices(
        _repos(world), get_access_guard(), idle_timeout=timedelta(hours=1)
    ).handle(ListOwnDevicesQuery(), _actor(alice.id))

    assert listed == []


async def test_several_sessions_on_one_device_are_grouped(
    world: World, make_user: MakeUser, cases: Cases
) -> None:
    """Sessions sharing a device are listed together under it."""
    alice = make_user("alice")
    await world.users.add(alice)
    result = await _sign_in(cases)
    device = await world.devices.get_by_token_hash(_hash(result.device_token))
    assert device is not None
    extra = Session.create(
        user_id=alice.id,
        token_hash="extra",
        now=datetime.now(UTC) - timedelta(minutes=5),
        ttl=timedelta(hours=1),
        device_id=device.id,
    )
    await world.sessions.add(extra)

    listed = await ListOwnDevices(_repos(world), get_access_guard()).handle(
        ListOwnDevicesQuery(), _actor(alice.id)
    )

    assert len(listed) == 1
    assert [s.session.id for s in listed[0].sessions] == [result.session_id, extra.id]


# --- revoking a device --------------------------------------------------------


async def test_revoking_a_device_ends_its_sessions_and_forgets_it(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """The other browser is signed out and loses its cookie's limit."""
    alice = make_user("alice")
    await world.users.add(alice)
    other = await _sign_in(cases)
    this = await _sign_in(cases)
    device = await world.devices.get_by_token_hash(_hash(other.device_token))
    assert device is not None

    ended = await RevokeOwnDevice(world.uow, get_access_guard()).handle(
        RevokeOwnDeviceCommand(device_id=device.id, current_session_id=this.session_id),
        _actor(alice.id),
    )

    assert ended == 1
    assert await world.devices.get(device.id) is None
    assert await world.sessions.get(other.session_id) is None
    assert await world.sessions.get(this.session_id)


async def test_the_current_device_cannot_be_revoked(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Revoking this browser is refused; signing out is the way to leave it."""
    alice = make_user("alice")
    await world.users.add(alice)
    this = await _sign_in(cases)
    device = await world.devices.get_by_token_hash(_hash(this.device_token))
    assert device is not None

    with pytest.raises(CurrentSessionError):
        await RevokeOwnDevice(world.uow, get_access_guard()).handle(
            RevokeOwnDeviceCommand(
                device_id=device.id, current_session_id=this.session_id
            ),
            _actor(alice.id),
        )


@pytest.mark.parametrize("whose", ["someone else's", "unknown"])
async def test_a_foreign_or_unknown_device_is_not_found(
    cases: Cases, world: World, make_user: MakeUser, whose: str
) -> None:
    """Another person's device looks exactly like one that does not exist."""
    alice = make_user("alice")
    await world.users.add(alice)
    await world.users.add(make_user("bob"))
    bobs = await _sign_in(cases, "bob")
    this = await _sign_in(cases)
    bob_device = await world.devices.get_by_token_hash(_hash(bobs.device_token))
    assert bob_device is not None
    device_id = bob_device.id if whose == "someone else's" else uuid.uuid7()

    with pytest.raises(DeviceNotFoundError):
        await RevokeOwnDevice(world.uow, get_access_guard()).handle(
            RevokeOwnDeviceCommand(
                device_id=device_id, current_session_id=this.session_id
            ),
            _actor(alice.id),
        )
    assert await world.devices.get(bob_device.id)
