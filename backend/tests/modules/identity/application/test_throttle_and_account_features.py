"""Sign-in throttling, disabled-account disclosure, last sign-in and unlock."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine

from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.session_token_generator import (
    InMemorySessionTokenGenerator,
)
from app.modules.identity.application.change_password import ChangePasswordCommand
from app.modules.identity.application.get_current_user import GetCurrentUserQuery
from app.modules.identity.application.has_administrator import (
    HasAdministrator,
    HasAdministratorQuery,
)
from app.modules.identity.application.list_users import ListUsersQuery
from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.set_own_display_name import (
    SetOwnDisplayNameCommand,
)
from app.modules.identity.application.sign_in import SignIn, SignInCommand
from app.modules.identity.application.sign_in_throttle import (
    SignInThrottle,
    ip_key,
    user_id_key,
    username_key,
)
from app.modules.identity.application.unlock_user import UnlockUserCommand
from app.modules.identity.application.update_user import UpdateUserCommand
from app.modules.identity.domain.errors import (
    AccountDisabledError,
    CurrentPasswordIncorrectError,
    InvalidCredentialsError,
    InvalidUserError,
    PasswordUnchangedError,
    SignInThrottledError,
    UserNotFoundError,
)
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from app.modules.identity.application.session_start import SignedInResult
    from app.modules.identity.ports.authenticator import (
        PasswordCredentials,
        VerifiedIdentity,
    )
    from tests.modules.identity.application.conftest import ActorFor, Cases
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=15)
MEMBER = Actor(id=uuid.uuid7(), roles=frozenset({"member"}))


async def _attempt(
    cases: Cases,
    username: str = "alice",
    password: str = "wrong-password",
    ip: str | None = None,
) -> None:
    await cases.sign_in.handle(
        SignInCommand(username=username, password=password, client_ip=ip),
        ANONYMOUS_ACTOR,
    )


async def _fail(
    cases: Cases, username: str = "alice", times: int = 1, ip: str | None = None
) -> None:
    for _ in range(times):
        with pytest.raises(InvalidCredentialsError):
            await _attempt(cases, username, ip=ip)


# --- last sign-in ---------------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_a_successful_sign_in_records_last_login_only(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Success stamps `last_login_at`; failures and session use do not."""
    user = make_user("alice")
    await world.users.add(user)

    await _fail(cases)
    assert user.last_login_at is None

    result = await _attempt_ok(cases)
    assert user.last_login_at == NOW

    user.last_login_at = NOW - timedelta(days=1)
    with time_machine.travel(NOW + timedelta(minutes=5), tick=False):
        await cases.current_user.handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )
    assert user.last_login_at == NOW - timedelta(days=1)


async def _attempt_ok(
    cases: Cases, username: str = "alice", ip: str | None = None
) -> SignedInResult:
    return await cases.sign_in.handle(
        SignInCommand(username=username, password="password-123", client_ip=ip),
        ANONYMOUS_ACTOR,
    )


# --- disabled accounts ----------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_a_disabled_account_is_revealed_only_after_the_right_password(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Right password: AccountDisabledError. Wrong password: the generic refusal."""
    user = make_user("alice")
    user.disable()
    await world.users.add(user)

    with pytest.raises(AccountDisabledError, match="has been disabled"):
        await _attempt_ok(cases)
    with pytest.raises(InvalidCredentialsError):
        await _attempt(cases)

    assert user.last_login_at is None
    assert await world.sessions.get_by_token_hash("anything") is None


@time_machine.travel(NOW, tick=False)
async def test_a_correct_password_on_a_disabled_account_is_not_a_failure(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """It neither counts toward the lock nor clears an existing count."""
    user = make_user("alice")
    user.disable()
    await world.users.add(user)
    await world.attempts.record_failure(
        username_key("alice"), limit=5, window=WINDOW, now=NOW
    )

    for _ in range(10):
        with pytest.raises(AccountDisabledError):
            await _attempt_ok(cases, ip="198.51.100.1")

    assert world.attempts.windows[username_key("alice")].count == 1
    assert ip_key("198.51.100.1") not in world.attempts.windows


# --- throttling -----------------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_the_sixth_attempt_is_refused_before_the_password_is_checked(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """After five failures even the right password gets a 429 with a wait."""
    await world.users.add(make_user("alice"))
    await _fail(cases, times=5)

    with pytest.raises(SignInThrottledError) as caught:
        await _attempt_ok(cases)

    assert caught.value.retry_after == 15 * 60


@time_machine.travel(NOW, tick=False)
async def test_unknown_usernames_throttle_exactly_like_real_ones(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """No existence oracle: ghost and alice lock after the same five failures."""
    await world.users.add(make_user("alice"))
    outcomes = []
    for name in ("ghost", "alice"):
        await _fail(cases, name, times=5)
        with pytest.raises(SignInThrottledError) as caught:
            await _attempt(cases, name)
        outcomes.append((str(caught.value), caught.value.retry_after))

    assert outcomes[0] == outcomes[1]


@time_machine.travel(NOW, tick=False)
async def test_the_username_key_ignores_case(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """`Alice` and `alice` share one counter."""
    await world.users.add(make_user("alice"))
    await _fail(cases, "Alice", times=3)
    await _fail(cases, "ALICE", times=2)

    with pytest.raises(SignInThrottledError):
        await _attempt(cases, "alice")


async def test_the_lock_ends_with_the_window(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """After 15 minutes the right password signs in again."""
    await world.users.add(make_user("alice"))
    with time_machine.travel(NOW, tick=False) as clock:
        await _fail(cases, times=5)
        clock.move_to(NOW + WINDOW - timedelta(seconds=1))
        with pytest.raises(SignInThrottledError):
            await _attempt_ok(cases)
        clock.move_to(NOW + WINDOW)
        await _attempt_ok(cases)


class _SpyHasher(InMemoryPasswordHasher):
    def __init__(self) -> None:
        self.verified: list[str] = []

    def verify(self, password: str, hashed: str) -> bool:
        self.verified.append(hashed)
        return super().verify(password, hashed)


class _NeverAuthenticator:
    def __init__(self) -> None:
        self.calls = 0

    async def authenticate(
        self, credentials: PasswordCredentials
    ) -> VerifiedIdentity | None:
        self.calls += 1
        return None


@time_machine.travel(NOW, tick=False)
async def test_a_locked_attempt_costs_a_hash_but_never_reaches_the_authenticator(
    world: World,
) -> None:
    """The lock check runs first; a decoy verify keeps the timing equal."""
    hasher = _SpyHasher()
    authenticator = _NeverAuthenticator()
    sign_in = SignIn(
        world.uow,
        authenticator,
        InMemorySessionTokenGenerator(),
        hasher,
        SignInThrottle(),
        decoy_hash="fake$decoy",
        session_ttl=timedelta(hours=1),
    )
    for _ in range(5):
        await world.attempts.record_failure(
            username_key("alice"), limit=5, window=WINDOW, now=NOW
        )

    with pytest.raises(SignInThrottledError):
        await sign_in.handle(
            SignInCommand(username="alice", password="password-123"), ANONYMOUS_ACTOR
        )

    assert authenticator.calls == 0
    assert hasher.verified == ["fake$decoy"]


@time_machine.travel(NOW, tick=False)
async def test_each_address_is_throttled_across_usernames(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Twenty failures from one address lock it, whatever names were tried."""
    await world.users.add(make_user("alice"))
    for i in range(20):
        await _fail(cases, f"ghost{i}", ip="203.0.113.7")

    with pytest.raises(SignInThrottledError):
        await _attempt_ok(cases, "alice", ip="203.0.113.7")
    # Another address, and the same account from it, are unaffected.
    await _attempt_ok(cases, "alice", ip="203.0.113.8")


@time_machine.travel(NOW, tick=False)
async def test_success_clears_the_username_counter_but_not_the_address(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A good sign-in resets the account's count; the address keeps its own."""
    await world.users.add(make_user("alice"))
    await _fail(cases, times=3, ip="203.0.113.7")

    await _attempt_ok(cases, ip="203.0.113.7")

    assert username_key("alice") not in world.attempts.windows
    assert world.attempts.windows[ip_key("203.0.113.7")].count == 3


@time_machine.travel(NOW, tick=False)
async def test_without_an_address_only_the_username_is_counted(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """No client address, no address counter."""
    await world.users.add(make_user("alice"))
    await _fail(cases, times=2)

    assert set(world.attempts.windows) == {username_key("alice")}


async def test_failures_sweep_counters_whose_window_ended(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Old rows are removed lazily on the next failure."""
    await world.users.add(make_user("alice"))
    with time_machine.travel(NOW, tick=False) as clock:
        await _fail(cases, "ghost")
        clock.move_to(NOW + WINDOW)
        await _fail(cases, "alice")

    assert set(world.attempts.windows) == {username_key("alice")}


def test_keys_are_hashes_not_raw_values() -> None:
    """Neither a username nor an address is stored in clear."""
    for key, raw in (
        (username_key("Alice"), "alice"),
        (ip_key("203.0.113.7"), "203.0.113.7"),
        (user_id_key(uuid.UUID(int=5)), str(uuid.UUID(int=5))),
    ):
        assert raw not in key.digest
        assert len(key.digest) == 64
    assert username_key("ALICE") == username_key("alice")
    assert username_key("alice") != ip_key("alice")


# --- change password throttling ------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_change_password_wrong_current_is_throttled_per_user_and_address(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Five wrong current passwords lock the user; success clears the count."""
    user = make_user("alice")
    await world.users.add(user)
    actor = actor_for(user)

    def wrong(ip: str | None = None) -> ChangePasswordCommand:
        return ChangePasswordCommand(
            current_password="not-it-at-all",
            new_password="a-much-better-one",
            client_ip=ip,
        )

    for _ in range(4):
        with pytest.raises(CurrentPasswordIncorrectError):
            await cases.change_password.handle(wrong("203.0.113.7"), actor)
    assert world.attempts.windows[user_id_key(user.id)].count == 4
    assert world.attempts.windows[ip_key("203.0.113.7")].count == 4

    result = await cases.change_password.handle(
        ChangePasswordCommand(
            current_password="password-123",
            new_password="a-much-better-one",
            client_ip="203.0.113.7",
        ),
        actor,
    )
    assert result.user is user
    assert user_id_key(user.id) not in world.attempts.windows
    assert ip_key("203.0.113.7") in world.attempts.windows

    for _ in range(5):
        with pytest.raises(CurrentPasswordIncorrectError):
            await cases.change_password.handle(wrong(), actor)
    with pytest.raises(SignInThrottledError):
        await cases.change_password.handle(wrong(), actor)


@time_machine.travel(NOW, tick=False)
async def test_change_password_is_throttled_by_address(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """An address that has failed too often is refused for any user."""
    user = make_user("alice")
    await world.users.add(user)
    await world.attempts.record_failure(
        ip_key("203.0.113.7"), limit=1, window=WINDOW, now=NOW
    )

    with pytest.raises(SignInThrottledError):
        await cases.change_password.handle(
            ChangePasswordCommand(
                current_password="password-123",
                new_password="a-much-better-one",
                client_ip="203.0.113.7",
            ),
            actor_for(user),
        )


async def test_change_password_rejects_the_same_password(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """A new password equal to the current one is refused and nothing changes."""
    user = make_user("alice")
    await world.users.add(user)
    original = user.password_hash

    with pytest.raises(PasswordUnchangedError) as caught:
        await cases.change_password.handle(
            ChangePasswordCommand(
                current_password="password-123", new_password="password-123"
            ),
            actor_for(user),
        )

    assert str(caught.value) == "The new password must differ from the current one."
    assert user.password_hash == original
    assert not world.uow.committed


# --- unlock ---------------------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_unlock_clears_only_the_username_counter(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """The account can sign in again; the address stays locked; flags unchanged."""
    user = make_user("alice")
    await world.users.add(user)
    await _fail(cases, times=5, ip="203.0.113.7")

    await cases.unlock_user.handle(UnlockUserCommand(user_id=user.id), admin_actor)

    assert username_key("alice") not in world.attempts.windows
    assert ip_key("203.0.113.7") in world.attempts.windows
    assert user.disabled is False
    await _attempt_ok(cases, ip="203.0.113.8")


async def test_unlock_is_idempotent_and_needs_a_known_user(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Unlocking an unlocked account is fine; an unknown id is not found."""
    user = make_user("alice")
    await world.users.add(user)
    command = UnlockUserCommand(user_id=user.id)

    await cases.unlock_user.handle(command, admin_actor)
    await cases.unlock_user.handle(command, admin_actor)

    with pytest.raises(UserNotFoundError):
        await cases.unlock_user.handle(
            UnlockUserCommand(user_id=uuid.uuid7()), admin_actor
        )


async def test_unlock_requires_the_permission(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A member cannot unlock anyone."""
    user = make_user("alice")
    await world.users.add(user)

    with pytest.raises(ForbiddenError):
        await cases.unlock_user.handle(UnlockUserCommand(user_id=user.id), MEMBER)


# --- listings -------------------------------------------------------------


@time_machine.travel(NOW, tick=False)
async def test_list_and_update_report_the_lock_state(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """`locked_until` is set only for a currently locked username."""
    alice = make_user("alice")
    await world.users.add(alice)
    await world.users.add(make_user("bob"))
    await _fail(cases, times=5)

    listed = {
        item.user.username: item.locked_until
        for item in await cases.list_users.handle(ListUsersQuery(), admin_actor)
    }
    updated = await cases.update_user.handle(
        UpdateUserCommand(user_id=alice.id, display_name="Alice B"), admin_actor
    )

    assert listed == {"alice": NOW + WINDOW, "bob": None}
    assert updated.locked_until == NOW + WINDOW


# --- display name ---------------------------------------------------------


async def test_set_own_display_name(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Anyone may rename themselves; the name is trimmed and validated."""
    user = make_user("alice")
    await world.users.add(user)

    renamed = await cases.set_own_display_name.handle(
        SetOwnDisplayNameCommand(display_name="  Alice B  "), actor_for(user)
    )

    assert renamed is user
    assert user.display_name == "Alice B"
    assert world.uow.committed
    with pytest.raises(InvalidUserError):
        await cases.set_own_display_name.handle(
            SetOwnDisplayNameCommand(display_name="  "), actor_for(user)
        )
    assert user.display_name == "Alice B"


async def test_set_own_display_name_for_a_vanished_user(
    cases: Cases, actor_for: ActorFor, make_user: MakeUser
) -> None:
    """An actor whose account is gone gets UserNotFoundError."""
    with pytest.raises(UserNotFoundError):
        await cases.set_own_display_name.handle(
            SetOwnDisplayNameCommand(display_name="X"), actor_for(make_user("ghost"))
        )


# --- permissions ----------------------------------------------------------


async def test_every_user_management_use_case_requires_its_permission(
    cases: Cases, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Each use case declares the permission the catalogue knows."""
    assert cases.create_user.required_permission is IdentityPermission.CREATE_USER
    assert cases.list_users.required_permission is IdentityPermission.LIST_USERS
    assert cases.update_user.required_permission is IdentityPermission.UPDATE_USER
    assert (
        cases.reset_password.required_permission
        is IdentityPermission.RESET_USER_PASSWORD
    )
    assert cases.unlock_user.required_permission is IdentityPermission.UNLOCK_USER
    with pytest.raises(ForbiddenError):
        await cases.list_users.handle(ListUsersQuery(), MEMBER)


# --- administrator check --------------------------------------------------


async def test_has_administrator_counts_enabled_administrators(
    world: World, make_user: MakeUser
) -> None:
    """Members and disabled administrators do not count."""
    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    query = HasAdministrator(repos)
    assert await query.handle(HasAdministratorQuery(), ANONYMOUS_ACTOR) is False

    await world.users.add(make_user("member"))
    gone = make_user("gone", role=Role.ADMIN)
    gone.disable()
    await world.users.add(gone)
    assert await query.handle(HasAdministratorQuery(), ANONYMOUS_ACTOR) is False

    await world.users.add(make_user("root", role=Role.ADMIN))
    assert await query.handle(HasAdministratorQuery(), ANONYMOUS_ACTOR) is True
