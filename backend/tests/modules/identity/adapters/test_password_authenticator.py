from datetime import UTC, datetime
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
from app.modules.identity.domain.errors import AccountDisabledError
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
    """The verified identity carries the username, display name and matched hash."""
    user = make_user("alice")
    await world.users.add(user)
    identity = await _authenticator(world).authenticate(_creds("ALICE"))
    assert identity == VerifiedIdentity(
        subject="alice", display_name="Alice", credential_hash=user.password_hash
    )


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
async def test_correct_password_for_a_disabled_user_is_revealed(
    world: World, make_user: MakeUser
) -> None:
    """Only a verified password learns the account is disabled."""
    user = make_user("alice")
    user.disable()
    await world.users.add(user)
    auth = _authenticator(world)

    with pytest.raises(AccountDisabledError):
        await auth.authenticate(_creds())
    assert await auth.authenticate(_creds(password="wrong-password")) is None


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


class _VerifyCountingHasher(InMemoryPasswordHasher):
    def __init__(self) -> None:
        self.verified: list[str] = []

    def verify(self, password: str, hashed: str) -> bool:
        self.verified.append(hashed)
        return super().verify(password, hashed)


@time_machine.travel(NOW, tick=False)
async def test_every_wrong_attempt_costs_one_verify(
    world: World, make_user: MakeUser
) -> None:
    """Unknown, disabled and wrong-password attempts all spend one verify."""
    disabled = make_user("gone")
    disabled.disable()
    await world.users.add(disabled)
    await world.users.add(make_user("alice"))
    hasher = _VerifyCountingHasher()
    auth = PasswordAuthenticator(world.uow, hasher, decoy_hash="fake$decoy")

    assert await auth.authenticate(_creds("nobody")) is None
    assert await auth.authenticate(_creds("gone", "wrong-password")) is None
    assert await auth.authenticate(_creds("alice", "wrong-password")) is None

    assert len(hasher.verified) == 3
    assert hasher.verified[0] == "fake$decoy"


class _MutatingHasher(InMemoryPasswordHasher):
    """Runs a callback while a verify is in flight, like a concurrent change."""

    def __init__(self, during_verify: Callable[[], None]) -> None:
        self._during_verify = during_verify

    def verify(self, password: str, hashed: str) -> bool:
        self._during_verify()
        return super().verify(password, hashed)


@time_machine.travel(NOW, tick=False)
async def test_success_is_rechecked_under_the_row_lock(
    world: World, make_user: MakeUser
) -> None:
    """A right password is confirmed against the locked row, after the check."""
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
    assert calls == ["alice"]


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
    with pytest.raises(AccountDisabledError):
        await auth.authenticate(_creds())


@time_machine.travel(NOW, tick=False)
async def test_password_changed_while_verifying_is_refused(
    world: World, make_user: MakeUser
) -> None:
    """A result for an old hash does not sign in against a new one."""
    user = make_user("alice")
    await world.users.add(user)
    new_hash = InMemoryPasswordHasher().hash("another-password")
    auth = PasswordAuthenticator(
        world.uow,
        _MutatingHasher(lambda: user.change_password(new_hash)),
        decoy_hash="fake$decoy",
    )
    assert await auth.authenticate(_creds()) is None
    assert user.password_hash == new_hash
