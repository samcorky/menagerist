from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine

from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.password_authenticator import (
    PasswordAuthenticator,
)
from app.modules.identity.adapters.security.password_hasher_registry import (
    PasswordHasherRegistry,
)
from app.modules.identity.adapters.security.scrypt_password_hasher import (
    ScryptPasswordHasher,
)
from app.modules.identity.domain.errors import SignInThrottledError
from app.modules.identity.ports.authenticator import (
    PasswordCredentials,
    VerifiedIdentity,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.identity.domain.user import User
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _authenticator(world: World, *, default: str = "fake") -> PasswordAuthenticator:
    registry = PasswordHasherRegistry(
        {"fake": InMemoryPasswordHasher(), "scrypt": ScryptPasswordHasher(n=2**4)},
        default=default,
    )
    return PasswordAuthenticator(
        world.uow, registry, decoy_hash=registry.hash("decoy-password")
    )


def _creds(
    username: str = "alice", password: str = "password-123"
) -> PasswordCredentials:
    return PasswordCredentials(username=username, password=password)


@time_machine.travel(NOW, tick=False)
async def test_valid_credentials_return_identity(
    world: World, make_user: MakeUser
) -> None:
    """The verified identity carries the username and display name."""
    await world.users.add(make_user("alice"))
    identity = await _authenticator(world).authenticate(_creds("ALICE"))
    assert identity == VerifiedIdentity(subject="alice", display_name="Alice")


@time_machine.travel(NOW, tick=False)
async def test_wrong_password_and_unknown_user_return_none(
    world: World, make_user: MakeUser
) -> None:
    """Failure never says which half was wrong."""
    await world.users.add(make_user("alice"))
    auth = _authenticator(world)
    assert await auth.authenticate(_creds(password="wrong-password")) is None
    assert await auth.authenticate(_creds("nobody")) is None


@time_machine.travel(NOW, tick=False)
async def test_failure_is_recorded_and_success_resets(
    world: World, make_user: MakeUser
) -> None:
    """A failure counts and commits; a later success clears it."""
    user = make_user("alice")
    await world.users.add(user)
    auth = _authenticator(world)

    await auth.authenticate(_creds(password="wrong-password"))
    assert user.failed_attempts == 1
    assert world.uow.committed is True

    assert await auth.authenticate(_creds()) is not None
    assert user.failed_attempts == 0


@time_machine.travel(NOW, tick=False)
async def test_disabled_user_cannot_sign_in(world: World, make_user: MakeUser) -> None:
    """A disabled account is refused even with the right password."""
    user = make_user("alice")
    user.disable()
    await world.users.add(user)
    assert await _authenticator(world).authenticate(_creds()) is None
    assert user.failed_attempts == 0


async def test_lockout_blocks_until_window_passes(
    world: World, make_user: MakeUser
) -> None:
    """Five failures lock the account, even for the right password, for 15 minutes."""
    user = make_user("alice")
    await world.users.add(user)
    auth = _authenticator(world)
    with time_machine.travel(NOW, tick=False) as clock:
        for _ in range(5):
            assert await auth.authenticate(_creds(password="wrong-password")) is None
        with pytest.raises(SignInThrottledError):
            await auth.authenticate(_creds())
        with pytest.raises(SignInThrottledError):
            await auth.authenticate(_creds(password="wrong-password"))
        clock.move_to(NOW + timedelta(minutes=15))
        assert await auth.authenticate(_creds()) is not None


@time_machine.travel(NOW, tick=False)
async def test_successful_sign_in_rewrites_outdated_hash(
    world: World, make_user: MakeUser
) -> None:
    """A hash in a non-default scheme is upgraded on success."""
    user = make_user("alice")
    await world.users.add(user)
    assert user.password_hash.startswith("fake$")

    assert await _authenticator(world, default="scrypt").authenticate(_creds())
    assert user.password_hash.startswith("scrypt$")
    assert await _authenticator(world, default="scrypt").authenticate(_creds())


class _CountingHasher(InMemoryPasswordHasher):
    def __init__(self) -> None:
        self.hash_calls = 0

    def hash(self, password: str) -> str:
        self.hash_calls += 1
        return super().hash(password)


@time_machine.travel(NOW, tick=False)
async def test_unknown_and_disabled_paths_never_hash(
    world: World, make_user: MakeUser
) -> None:
    """A fresh authenticator spends one verify, and no hash, on unknown names."""
    disabled = make_user("gone")
    disabled.disable()
    await world.users.add(disabled)
    hasher = _CountingHasher()
    auth = PasswordAuthenticator(world.uow, hasher, decoy_hash="fake$decoy")

    assert await auth.authenticate(_creds("nobody")) is None
    assert await auth.authenticate(_creds("gone")) is None
    assert hasher.hash_calls == 0


class _MutatingHasher(InMemoryPasswordHasher):
    """Runs a callback while a verify is in flight, like a concurrent change."""

    def __init__(self, during_verify: Callable[[], None]) -> None:
        self._during_verify = during_verify

    def verify(self, password: str, hashed: str) -> bool:
        self._during_verify()
        return super().verify(password, hashed)


@time_machine.travel(NOW, tick=False)
async def test_outcome_is_recorded_under_the_row_lock(
    world: World, make_user: MakeUser
) -> None:
    """Recording goes through the locking lookup, after the password check."""
    await world.users.add(make_user("alice"))
    calls: list[str] = []
    original = world.users.get_by_username_for_update

    async def spy(username: str) -> User | None:
        calls.append(username)
        return await original(username)

    world.users.get_by_username_for_update = spy  # type: ignore[method-assign]
    auth = _authenticator(world)

    assert await auth.authenticate(_creds()) is not None
    assert await auth.authenticate(_creds(password="wrong-password")) is None
    assert calls == ["alice"] * 2


@time_machine.travel(NOW, tick=False)
async def test_disabled_or_locked_state_is_checked_before_verifying(
    world: World, make_user: MakeUser
) -> None:
    """Disabled accounts and locked accounts never reach the locking lookup."""
    user = make_user("alice")
    await world.users.add(user)
    auth = _authenticator(world)
    user.disable()
    assert await auth.authenticate(_creds()) is None
    user.enable()
    for _ in range(5):
        user.record_failure(NOW)
    with pytest.raises(SignInThrottledError):
        await auth.authenticate(_creds())


@time_machine.travel(NOW, tick=False)
async def test_account_disabled_while_verifying_is_refused(
    world: World, make_user: MakeUser
) -> None:
    """An admin disabling the account mid-verify wins over the right password."""
    user = make_user("alice")
    await world.users.add(user)
    auth = PasswordAuthenticator(
        world.uow, _MutatingHasher(user.disable), decoy_hash="fake$decoy"
    )
    assert await auth.authenticate(_creds()) is None
    assert user.failed_attempts == 0


@time_machine.travel(NOW, tick=False)
async def test_password_changed_while_verifying_is_refused(
    world: World, make_user: MakeUser
) -> None:
    """A result for an old hash does not sign in or count against a new one."""
    user = make_user("alice")
    await world.users.add(user)
    new_hash = InMemoryPasswordHasher().hash("another-password")
    auth = PasswordAuthenticator(
        world.uow,
        _MutatingHasher(lambda: user.change_password(new_hash)),
        decoy_hash="fake$decoy",
    )
    assert await auth.authenticate(_creds()) is None
    assert user.failed_attempts == 0
    assert user.password_hash == new_hash


@time_machine.travel(NOW, tick=False)
async def test_account_locked_while_verifying_is_throttled(
    world: World, make_user: MakeUser
) -> None:
    """Failures recorded by others mid-verify lock the attempt out."""
    user = make_user("alice")
    await world.users.add(user)

    def lock() -> None:
        for _ in range(5):
            user.record_failure(NOW)

    auth = PasswordAuthenticator(
        world.uow, _MutatingHasher(lock), decoy_hash="fake$decoy"
    )
    with pytest.raises(SignInThrottledError):
        await auth.authenticate(_creds())
