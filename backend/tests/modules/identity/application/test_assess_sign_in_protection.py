"""Locked accounts, unknown names and addresses are counted without naming anyone."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.application.assess_sign_in_protection import (
    AssessSignInProtection,
    AssessSignInProtectionQuery,
    SignInProtection,
)
from app.modules.identity.application.sign_in_throttle import (
    device_key,
    ip_key,
    token_ip_key,
    user_id_key,
    username_key,
)
from app.modules.identity.domain.throttle import AttemptWindow, ThrottleKey
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)
QUERY = AssessSignInProtectionQuery(now=NOW)


def _use_case(world: World) -> AssessSignInProtection:
    return AssessSignInProtection(
        IdentityRepos(
            users=world.users,
            sessions=world.sessions,
            attempts=world.attempts,
            tokens=world.tokens,
            devices=world.devices,
        ),
        get_access_guard(),
    )


def _lock(world: World, key: ThrottleKey, *, until: timedelta | None) -> None:
    """Store a counter for `key` that is locked for `until` from NOW, or not locked."""
    world.attempts.windows[key] = AttemptWindow(
        count=5,
        window_start=NOW - timedelta(minutes=5),
        locked_until=None if until is None else NOW + until,
    )


async def test_nothing_locked_reports_nothing(world: World) -> None:
    """A quiet instance counts as zero everywhere."""
    assert await _use_case(world).handle(QUERY, SYSTEM_ACTOR) == SignInProtection()


async def test_locked_accounts_are_matched_by_username_or_user_id(
    world: World, make_user: MakeUser
) -> None:
    """Either counter locks an account, and an account counts once."""
    alice, bob, carol = make_user("alice"), make_user("bob"), make_user("carol")
    for user in (alice, bob, carol):
        await world.users.add(user)
    _lock(world, username_key("alice"), until=timedelta(minutes=10))
    _lock(world, user_id_key(bob.id), until=timedelta(minutes=10))
    _lock(world, username_key("bob"), until=timedelta(minutes=10))

    result = await _use_case(world).handle(QUERY, SYSTEM_ACTOR)

    assert result.locked_accounts == 2
    assert result.unknown_names == 0


async def test_usernames_are_matched_case_insensitively(
    world: World, make_user: MakeUser
) -> None:
    """The sign-in key lowercases the typed name, so ALICE locks alice."""
    await world.users.add(make_user("alice"))
    _lock(world, username_key("ALICE"), until=timedelta(minutes=10))

    assert (await _use_case(world).handle(QUERY, SYSTEM_ACTOR)).locked_accounts == 1


async def test_locked_names_without_an_account_are_counted_apart(
    world: World, make_user: MakeUser
) -> None:
    """A locked name that matches nobody is a guessing signal, not a locked account."""
    await world.users.add(make_user("alice"))
    _lock(world, username_key("admin"), until=timedelta(minutes=10))
    _lock(world, username_key("root"), until=timedelta(minutes=10))

    result = await _use_case(world).handle(QUERY, SYSTEM_ACTOR)

    assert result.locked_accounts == 0
    assert result.unknown_names == 2


async def test_sign_in_and_token_addresses_both_count(world: World) -> None:
    """Both address counters lock a client out of something."""
    _lock(world, ip_key("203.0.113.7"), until=timedelta(minutes=10))
    _lock(world, token_ip_key("203.0.113.8"), until=timedelta(minutes=10))
    _lock(world, ip_key("203.0.113.9"), until=timedelta(minutes=10))

    assert (await _use_case(world).handle(QUERY, SYSTEM_ACTOR)).locked_addresses == 3


async def test_expired_and_unlocked_counters_are_ignored(
    world: World, make_user: MakeUser
) -> None:
    """Failures below the limit and locks that have ended are not locks."""
    await world.users.add(make_user("alice"))
    _lock(world, username_key("alice"), until=None)
    _lock(world, ip_key("203.0.113.7"), until=-timedelta(minutes=1))
    _lock(world, ip_key("203.0.113.8"), until=timedelta())

    assert await _use_case(world).handle(QUERY, SYSTEM_ACTOR) == SignInProtection()


async def test_locked_browsers_are_not_counted(world: World) -> None:
    """A remembered browser's lock does not stop the account signing in elsewhere."""
    _lock(world, device_key(uuid.uuid4()), until=timedelta(minutes=10))

    assert await _use_case(world).handle(QUERY, SYSTEM_ACTOR) == SignInProtection()


async def test_only_the_system_actor_may_ask(world: World) -> None:
    """The readiness boundary owns this query."""
    with pytest.raises(ForbiddenError):
        await _use_case(world).handle(QUERY, Actor(id=uuid.uuid4()))
