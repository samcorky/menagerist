"""Password-change races, attempt reservation, lock clearing and sign-in logging."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine
from structlog.testing import capture_logs

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.password_authenticator import (
    PasswordAuthenticator,
)
from app.modules.identity.adapters.security.session_token_generator import (
    InMemorySessionTokenGenerator,
)
from app.modules.identity.application.change_password import ChangePasswordCommand
from app.modules.identity.application.reset_password import ResetPasswordCommand
from app.modules.identity.application.sign_in import SignIn, SignInCommand
from app.modules.identity.application.sign_in_throttle import (
    SignInThrottle,
    ip_key,
    user_id_key,
    username_key,
)
from app.modules.identity.application.unlock_user import UnlockUserCommand
from app.modules.identity.domain.errors import (
    CurrentPasswordIncorrectError,
    InvalidCredentialsError,
    SignInThrottledError,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.modules.identity.ports.authenticator import (
        Authenticator,
        PasswordCredentials,
        VerifiedIdentity,
    )
    from tests.modules.identity.application.conftest import ActorFor, Cases
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=15)
TTL = timedelta(hours=1)
SECRET = "s3cret-guess-xyz"


def _admin() -> Actor:
    return Actor(id=uuid.uuid7(), roles=frozenset({"admin"}))


class _AfterAuthenticator:
    """Runs `action` right after the real authenticator verified the password."""

    def __init__(
        self, inner: Authenticator, action: Callable[[], Awaitable[object]]
    ) -> None:
        self._inner = inner
        self._action = action

    async def authenticate(
        self, credentials: PasswordCredentials
    ) -> VerifiedIdentity | None:
        identity = await self._inner.authenticate(credentials)
        await self._action()
        return identity


async def test_a_password_changed_after_the_check_voids_the_sign_in(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """No session is minted from a password that was replaced mid sign-in."""
    user = make_user("alice")
    await world.users.add(user)
    hasher = InMemoryPasswordHasher()

    async def change() -> None:
        await cases.change_password.handle(
            ChangePasswordCommand(
                current_password="password-123", new_password="a-much-better-one"
            ),
            actor_for(user),
        )

    sign_in = SignIn(
        world.uow,
        get_access_guard(),
        _AfterAuthenticator(
            PasswordAuthenticator(world.uow, hasher, decoy_hash="fake$decoy"), change
        ),
        InMemorySessionTokenGenerator(),
        hasher,
        SignInThrottle(),
        decoy_hash="fake$decoy",
        session_ttl=TTL,
    )

    with pytest.raises(InvalidCredentialsError):
        await sign_in.handle(
            SignInCommand(username="alice", password="password-123"), ANONYMOUS_ACTOR
        )

    # Only the session ChangePassword started exists; sign-in added none.
    assert len(world.sessions._sessions) == 1
    assert user.last_login_at is None


class _CountingHasher(InMemoryPasswordHasher):
    def __init__(self) -> None:
        self.guesses = 0

    def verify(self, password: str, hashed: str) -> bool:
        if password != "decoy":
            self.guesses += 1
        return super().verify(password, hashed)


def _sign_in_with(world: World, hasher: _CountingHasher) -> SignIn:
    return SignIn(
        world.uow,
        get_access_guard(),
        PasswordAuthenticator(world.uow, hasher, decoy_hash="fake$decoy"),
        InMemorySessionTokenGenerator(),
        hasher,
        SignInThrottle(),
        decoy_hash=hasher.hash("decoy"),
        session_ttl=TTL,
    )


async def test_parallel_guesses_never_verify_more_than_the_limit(
    world: World, make_user: MakeUser
) -> None:
    """Forty parallel guesses from distinct addresses: five are checked, no more."""
    await world.users.add(make_user("alice"))
    hasher = _CountingHasher()
    sign_in = _sign_in_with(world, hasher)

    async def guess(i: int) -> str:
        try:
            await sign_in.handle(
                SignInCommand(
                    username="alice", password=f"wrong-{i}", client_ip=f"10.0.0.{i}"
                ),
                ANONYMOUS_ACTOR,
            )
        except (InvalidCredentialsError, SignInThrottledError) as error:
            return type(error).__name__
        raise AssertionError("a wrong password signed in")

    outcomes = await asyncio.gather(*(guess(i) for i in range(40)))

    assert hasher.guesses == 5
    assert outcomes.count("InvalidCredentialsError") == 5
    assert outcomes.count("SignInThrottledError") == 35


async def test_an_unknown_username_is_reserved_and_locked_the_same_way(
    world: World,
) -> None:
    """Names with no account hit the same limit with the same refusal."""
    sign_in = _sign_in_with(world, _CountingHasher())

    async def guess() -> str:
        try:
            await sign_in.handle(
                SignInCommand(username="ghost", password="x"), ANONYMOUS_ACTOR
            )
        except (InvalidCredentialsError, SignInThrottledError) as error:
            return type(error).__name__
        return "signed in"

    outcomes = [await guess() for _ in range(7)]
    assert outcomes == ["InvalidCredentialsError"] * 5 + ["SignInThrottledError"] * 2


@time_machine.travel(NOW, tick=False)
async def test_success_clears_the_username_counter_and_refunds_the_address(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Failures from an address stay counted; a correct sign-in adds none."""
    await world.users.add(make_user("alice"))
    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            await cases.sign_in.handle(
                SignInCommand(username="alice", password="no", client_ip="10.1.1.1"),
                ANONYMOUS_ACTOR,
            )

    await cases.sign_in.handle(
        SignInCommand(username="alice", password="password-123", client_ip="10.1.1.1"),
        ANONYMOUS_ACTOR,
    )

    assert username_key("alice") not in world.attempts.windows
    assert world.attempts.windows[ip_key("10.1.1.1")].count == 2


@time_machine.travel(NOW, tick=False)
async def test_change_password_reserves_before_checking_and_clears_on_success(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Five wrong guesses are checked; the sixth is refused unchecked."""
    user = make_user("alice")
    await world.users.add(user)
    original = user.password_hash

    def command(current: str) -> ChangePasswordCommand:
        return ChangePasswordCommand(
            current_password=current,
            new_password="a-much-better-one",
            client_ip="10.2.2.2",
        )

    for _ in range(5):
        with pytest.raises(CurrentPasswordIncorrectError):
            await cases.change_password.handle(command("nope"), actor_for(user))
    with pytest.raises(SignInThrottledError):
        await cases.change_password.handle(command("password-123"), actor_for(user))
    assert user.password_hash == original

    await cases.unlock_user.handle(UnlockUserCommand(user_id=user.id), _admin())
    await cases.change_password.handle(command("password-123"), actor_for(user))

    assert user_id_key(user.id) not in world.attempts.windows
    # Five wrong guesses and the refused one stay counted; the success is refunded.
    assert world.attempts.windows[ip_key("10.2.2.2")].count == 6


async def _lock_password_change(world: World, user_id: uuid.UUID) -> None:
    for _ in range(5):
        await world.attempts.record_failure(
            user_id_key(user_id), limit=5, window=WINDOW, now=NOW
        )


@time_machine.travel(NOW, tick=False)
async def test_reset_password_also_clears_the_password_change_counter(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """An administrator's reset lifts the user-id keyed lock too."""
    user = make_user("alice")
    await world.users.add(user)
    await _lock_password_change(world, user.id)

    await cases.reset_password.handle(
        ResetPasswordCommand(user_id=user.id, password="a-brand-new-one"), _admin()
    )

    assert user_id_key(user.id) not in world.attempts.windows


@time_machine.travel(NOW, tick=False)
async def test_unlock_also_clears_the_password_change_counter(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Unlocking lifts the user-id keyed lock as well as the username one."""
    user = make_user("alice")
    await world.users.add(user)
    await _lock_password_change(world, user.id)

    await cases.unlock_user.handle(UnlockUserCommand(user_id=user.id), _admin())

    assert user_id_key(user.id) not in world.attempts.windows


@time_machine.travel(NOW, tick=False)
async def test_failed_and_throttled_sign_ins_are_logged_without_secrets(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Events carry the address and a short hash, never the name or password."""
    await world.users.add(make_user("alice"))
    with capture_logs() as logs:
        for _ in range(6):
            with pytest.raises((InvalidCredentialsError, SignInThrottledError)):
                await cases.sign_in.handle(
                    SignInCommand(
                        username="Alice", password=SECRET, client_ip="192.0.2.9"
                    ),
                    ANONYMOUS_ACTOR,
                )

    events = [entry["event"] for entry in logs]
    assert events == ["sign_in_failed"] * 5 + ["sign_in_throttled"]
    short = username_key("alice").digest[:12]
    for entry in logs:
        assert entry["log_level"] == "warning"
        assert entry["client_ip"] == "192.0.2.9"
        assert entry["username_hash"] == short
    dump = repr(logs).lower()
    assert "alice" not in dump
    assert SECRET not in dump
