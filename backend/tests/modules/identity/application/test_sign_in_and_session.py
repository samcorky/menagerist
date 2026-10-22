import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.security.session_token_generator import (
    InMemorySessionTokenGenerator,
)
from app.modules.identity.application.client_device import ClientDevice
from app.modules.identity.application.get_current_user import (
    GetCurrentUser,
    GetCurrentUserQuery,
)
from app.modules.identity.application.sign_in import SignInCommand
from app.modules.identity.application.sign_out import SignOutCommand
from app.modules.identity.domain.errors import (
    InvalidCredentialsError,
    SignInThrottledError,
)
from app.modules.identity.domain.session import Session
from app.shared_kernel.actor import ANONYMOUS_ACTOR

if TYPE_CHECKING:
    from app.modules.identity.application.session_start import SignedInResult
    from tests.modules.identity.application.conftest import Cases
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
TTL = timedelta(hours=1)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _sign_in(
    cases: Cases, username: str = "alice", password: str = "password-123"
) -> SignedInResult:
    return await cases.sign_in.handle(
        SignInCommand(username=username, password=password), ANONYMOUS_ACTOR
    )


@time_machine.travel(NOW, tick=False)
async def test_sign_in_creates_a_session_storing_only_the_token_hash(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A good sign-in returns the token; storage holds just its sha256."""
    user = make_user("alice")
    await world.users.add(user)

    result = await _sign_in(cases, "ALICE")

    assert result.user is user
    assert result.token == "token-1"
    assert world.uow.committed
    stored = await world.sessions.get_by_token_hash(_hash("token-1"))
    assert stored is not None
    assert stored.user_id == user.id
    assert stored.expires_at == NOW + TTL
    assert await world.sessions.get_by_token_hash("token-1") is None


@time_machine.travel(NOW, tick=False)
async def test_sign_in_stores_device_details_on_created_session(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Device details and client IP pass through into the created session."""
    user = make_user("alice")
    await world.users.add(user)

    device = ClientDevice(user_agent="CustomAgent/1.0", platform="Linux", mobile=False)
    result = await cases.sign_in.handle(
        SignInCommand(
            username="alice",
            password="password-123",
            client_ip="192.0.2.1",
            device=device,
        ),
        ANONYMOUS_ACTOR,
    )

    stored = await world.sessions.get_by_token_hash(_hash(result.token))
    assert stored is not None
    assert stored.user_agent == "CustomAgent/1.0"
    assert stored.client_ip == "192.0.2.1"
    assert stored.client_platform == "Linux"
    assert stored.client_mobile is False


@time_machine.travel(NOW, tick=False)
async def test_sign_in_sweeps_expired_sessions(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A successful sign-in removes sessions that have already expired."""
    user = make_user("alice")
    await world.users.add(user)
    stale = Session.create(
        user_id=user.id, token_hash="stale", now=NOW - 2 * TTL, ttl=TTL
    )
    live = Session.create(user_id=user.id, token_hash="live", now=NOW, ttl=TTL)
    await world.sessions.add(stale)
    await world.sessions.add(live)

    await _sign_in(cases)

    assert await world.sessions.get_by_token_hash("stale") is None
    assert await world.sessions.get_by_token_hash("live") is not None


@time_machine.travel(NOW, tick=False)
@pytest.mark.parametrize("case", ["unknown", "wrong", "disabled"])
async def test_every_failure_gives_the_same_generic_error(
    case: str, cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Unknown user and wrong passwords (any account state) are indistinguishable."""
    user = make_user("alice")
    if case == "disabled":
        user.disable()
    await world.users.add(user)
    username = "ghost" if case == "unknown" else "alice"
    password = "wrong-password"

    with pytest.raises(InvalidCredentialsError) as caught:
        await _sign_in(cases, username, password)

    assert str(caught.value) == "Incorrect username or password."
    assert await world.sessions.get_by_token_hash(_hash("token-1")) is None


@time_machine.travel(NOW, tick=False)
async def test_throttled_account_raises_with_retry_after(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """After five failures the sixth attempt is refused with a wait time."""
    await world.users.add(make_user("alice"))
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            await _sign_in(cases, password="wrong-password")

    with pytest.raises(SignInThrottledError) as caught:
        await _sign_in(cases)

    assert caught.value.retry_after == 15 * 60


async def test_current_user_resolves_a_live_session(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """The token from sign-in resolves to the user; unknown tokens do not."""
    await world.users.add(make_user("alice"))
    with time_machine.travel(NOW, tick=False):
        result = await _sign_in(cases)
        found = await cases.current_user.handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )
        missing = await cases.current_user.handle(
            GetCurrentUserQuery(token="nope"), ANONYMOUS_ACTOR
        )

    assert found is not None
    assert found.user is result.user
    assert found.session_id == result.session_id
    assert missing is None


async def test_current_user_rejects_and_removes_an_expired_session(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """A session past its expiry resolves to nobody and is deleted."""
    await world.users.add(make_user("alice"))
    with time_machine.travel(NOW, tick=False):
        result = await _sign_in(cases)
    with time_machine.travel(NOW + TTL + timedelta(seconds=1), tick=False):
        found = await cases.current_user.handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )

    assert found is None
    assert await world.sessions.get_by_token_hash(_hash(result.token)) is None


async def test_current_user_rejects_a_disabled_account(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Disabling an account ends its access even before sessions are purged."""
    user = make_user("alice")
    await world.users.add(user)
    with time_machine.travel(NOW, tick=False):
        result = await _sign_in(cases)
        user.disable()
        found = await cases.current_user.handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )

    assert found is None


async def test_last_seen_updates_at_most_once_a_minute(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Activity within a minute is not written; later activity is."""
    await world.users.add(make_user("alice"))
    with time_machine.travel(NOW, tick=False):
        result = await _sign_in(cases)
    session = await world.sessions.get_by_token_hash(_hash(result.token))
    assert session is not None

    with time_machine.travel(NOW + timedelta(seconds=59), tick=False):
        await cases.current_user.handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )
    assert session.last_seen_at == NOW

    later = NOW + timedelta(seconds=60)
    with time_machine.travel(later, tick=False):
        await cases.current_user.handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )
    assert session.last_seen_at == later


@time_machine.travel(NOW, tick=False)
async def test_sign_out_removes_the_session_and_ignores_unknown_tokens(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Signing out deletes only that session."""
    await world.users.add(make_user("alice"))
    first = await _sign_in(cases)
    second = await _sign_in(cases)

    await cases.sign_out.handle(SignOutCommand(token=first.token), ANONYMOUS_ACTOR)
    await cases.sign_out.handle(SignOutCommand(token="unknown"), ANONYMOUS_ACTOR)

    first_user = await cases.current_user.handle(
        GetCurrentUserQuery(token=first.token), ANONYMOUS_ACTOR
    )
    second_user = await cases.current_user.handle(
        GetCurrentUserQuery(token=second.token), ANONYMOUS_ACTOR
    )
    assert first_user is None
    assert second_user is not None


IDLE = timedelta(minutes=30)


def _idle_aware(cases: Cases, world: World) -> GetCurrentUser:
    return GetCurrentUser(
        world.uow,
        get_access_guard(),
        InMemorySessionTokenGenerator(),
        idle_timeout=IDLE,
    )


async def test_idle_limit_is_off_by_default(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Without an idle timeout a session unused until its expiry still works."""
    await world.users.add(make_user("alice"))
    with time_machine.travel(NOW, tick=False):
        result = await _sign_in(cases)
    with time_machine.travel(NOW + TTL - timedelta(seconds=1), tick=False):
        found = await cases.current_user.handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )

    assert found is not None


async def test_an_idle_session_is_rejected_and_removed_like_an_expired_one(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Unused for longer than the limit (but inside the TTL): nobody, row gone."""
    await world.users.add(make_user("alice"))
    with time_machine.travel(NOW, tick=False):
        result = await _sign_in(cases)
    idle_aware = _idle_aware(cases, world)
    with time_machine.travel(NOW + IDLE + timedelta(seconds=1), tick=False):
        found = await idle_aware.handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )

    assert found is None
    assert await world.sessions.get_by_token_hash(_hash(result.token)) is None
    assert world.uow.committed is True


async def test_the_idle_boundary_is_still_active(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Exactly at the limit the session is kept."""
    await world.users.add(make_user("alice"))
    with time_machine.travel(NOW, tick=False):
        result = await _sign_in(cases)
    with time_machine.travel(NOW + IDLE, tick=False):
        found = await _idle_aware(cases, world).handle(
            GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
        )

    assert found is not None


async def test_activity_keeps_a_session_alive_until_the_hard_cap(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Regular use never goes idle, but the TTL still ends the session."""
    await world.users.add(make_user("alice"))
    idle_aware = _idle_aware(cases, world)
    query = GetCurrentUserQuery
    with time_machine.travel(NOW, tick=False):
        result = await _sign_in(cases)
    for minutes in (25, 50):
        with time_machine.travel(NOW + timedelta(minutes=minutes), tick=False):
            assert (
                await idle_aware.handle(query(token=result.token), ANONYMOUS_ACTOR)
                is not None
            )
    with time_machine.travel(NOW + TTL + timedelta(seconds=1), tick=False):
        capped = await idle_aware.handle(query(token=result.token), ANONYMOUS_ACTOR)

    assert capped is None
