import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine
from structlog.testing import capture_logs

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.application.list_own_sessions import (
    ListOwnSessions,
    ListOwnSessionsQuery,
)
from app.modules.identity.application.revoke_other_sessions import (
    RevokeOtherSessions,
    RevokeOtherSessionsCommand,
)
from app.modules.identity.application.revoke_own_session import (
    RevokeOwnSession,
    RevokeOwnSessionCommand,
)
from app.modules.identity.domain.errors import CurrentSessionError, SessionNotFoundError
from app.modules.identity.domain.session import Session
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
TTL = timedelta(hours=24)
IDLE_TIMEOUT = timedelta(hours=2)


def _make_actor(user_id: uuid.UUID) -> Actor:
    return Actor(id=user_id, roles=frozenset({"member"}))


@time_machine.travel(NOW, tick=False)
async def test_list_own_sessions_returns_active_sessions_newest_first(
    world: World, make_user: MakeUser
) -> None:
    """Active sessions are returned newest first with current flag."""
    alice = make_user("alice")
    await world.users.add(alice)

    s1 = Session.create(
        user_id=alice.id,
        token_hash="hash-1",
        now=NOW - timedelta(hours=3),
        ttl=TTL,
        user_agent="BrowserA",
        client_ip="192.0.2.1",
    )
    s1.seen(NOW - timedelta(hours=1))

    s2 = Session.create(
        user_id=alice.id,
        token_hash="hash-2",
        now=NOW - timedelta(hours=2),
        ttl=TTL,
        user_agent="BrowserB",
        client_ip="192.0.2.2",
    )
    s2.seen(NOW - timedelta(minutes=10))

    await world.sessions.add(s1)
    await world.sessions.add(s2)

    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    handler = ListOwnSessions(repos, get_access_guard(), idle_timeout=IDLE_TIMEOUT)

    actor = _make_actor(alice.id)
    results = await handler.handle(
        ListOwnSessionsQuery(current_session_id=s2.id), actor
    )

    assert len(results) == 2
    assert results[0].session.id == s2.id
    assert results[0].current is True
    assert results[1].session.id == s1.id
    assert results[1].current is False


@time_machine.travel(NOW, tick=False)
async def test_list_own_sessions_excludes_expired_and_idle_sessions(
    world: World, make_user: MakeUser
) -> None:
    """Expired or idle sessions are excluded from the results."""
    alice = make_user("alice")
    await world.users.add(alice)

    # Active session
    active = Session.create(
        user_id=alice.id,
        token_hash="hash-active",
        now=NOW - timedelta(minutes=30),
        ttl=TTL,
    )
    active.seen(NOW - timedelta(minutes=5))

    # Expired session (expires_at in past)
    expired = Session.create(
        user_id=alice.id,
        token_hash="hash-expired",
        now=NOW - timedelta(days=2),
        ttl=timedelta(hours=1),
    )

    # Idle session (last_seen_at older than idle timeout)
    idle = Session.create(
        user_id=alice.id,
        token_hash="hash-idle",
        now=NOW - timedelta(hours=5),
        ttl=TTL,
    )
    idle.seen(NOW - timedelta(hours=3))

    await world.sessions.add(active)
    await world.sessions.add(expired)
    await world.sessions.add(idle)

    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    handler = ListOwnSessions(repos, get_access_guard(), idle_timeout=IDLE_TIMEOUT)

    actor = _make_actor(alice.id)
    results = await handler.handle(
        ListOwnSessionsQuery(current_session_id=active.id), actor
    )

    assert len(results) == 1
    assert results[0].session.id == active.id
    assert results[0].current is True


@time_machine.travel(NOW, tick=False)
async def test_list_own_sessions_excludes_other_users_sessions(
    world: World, make_user: MakeUser
) -> None:
    """Only sessions belonging to the caller are returned."""
    alice = make_user("alice")
    bob = make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)

    alice_session = Session.create(
        user_id=alice.id, token_hash="hash-alice", now=NOW, ttl=TTL
    )
    bob_session = Session.create(
        user_id=bob.id, token_hash="hash-bob", now=NOW, ttl=TTL
    )
    await world.sessions.add(alice_session)
    await world.sessions.add(bob_session)

    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    handler = ListOwnSessions(repos, get_access_guard(), idle_timeout=IDLE_TIMEOUT)

    actor = _make_actor(alice.id)
    results = await handler.handle(
        ListOwnSessionsQuery(current_session_id=alice_session.id), actor
    )

    assert len(results) == 1
    assert results[0].session.id == alice_session.id


@time_machine.travel(NOW, tick=False)
async def test_list_own_sessions_with_unknown_or_none_current_session(
    world: World, make_user: MakeUser
) -> None:
    """When current_session_id is None or unmatched, all current flags are False."""
    alice = make_user("alice")
    await world.users.add(alice)

    s1 = Session.create(user_id=alice.id, token_hash="hash-1", now=NOW, ttl=TTL)
    await world.sessions.add(s1)

    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    handler = ListOwnSessions(repos, get_access_guard(), idle_timeout=IDLE_TIMEOUT)

    actor = _make_actor(alice.id)
    results1 = await handler.handle(
        ListOwnSessionsQuery(current_session_id=None), actor
    )
    assert len(results1) == 1
    assert results1[0].current is False

    results2 = await handler.handle(
        ListOwnSessionsQuery(current_session_id=uuid.uuid7()), actor
    )
    assert len(results2) == 1
    assert results2[0].current is False


@time_machine.travel(NOW, tick=False)
async def test_revoke_own_session_success(world: World, make_user: MakeUser) -> None:
    """Revoking another of the caller's sessions deletes it and logs."""
    alice = make_user("alice")
    await world.users.add(alice)

    current_session = Session.create(
        user_id=alice.id, token_hash="hash-curr", now=NOW, ttl=TTL
    )
    other_session = Session.create(
        user_id=alice.id, token_hash="hash-other", now=NOW, ttl=TTL
    )
    await world.sessions.add(current_session)
    await world.sessions.add(other_session)

    handler = RevokeOwnSession(world.uow, get_access_guard())
    actor = _make_actor(alice.id)

    with capture_logs() as logs:
        await handler.handle(
            RevokeOwnSessionCommand(
                session_id=other_session.id,
                current_session_id=current_session.id,
            ),
            actor,
        )

    assert await world.sessions.get(other_session.id) is None
    assert await world.sessions.get(current_session.id) is not None
    assert world.uow.committed
    assert any(
        log.get("event") == "session revoked"
        and log.get("session_id") == other_session.id
        and log.get("user_id") == alice.id
        for log in logs
    )


@time_machine.travel(NOW, tick=False)
async def test_revoke_own_session_refuses_current_session(
    world: World, make_user: MakeUser
) -> None:
    """Revoking the current session raises CurrentSessionError (409)."""
    alice = make_user("alice")
    await world.users.add(alice)

    current_session = Session.create(
        user_id=alice.id, token_hash="hash-curr", now=NOW, ttl=TTL
    )
    await world.sessions.add(current_session)

    handler = RevokeOwnSession(world.uow, get_access_guard())
    actor = _make_actor(alice.id)

    with pytest.raises(CurrentSessionError, match="Cannot revoke the current session"):
        await handler.handle(
            RevokeOwnSessionCommand(
                session_id=current_session.id,
                current_session_id=current_session.id,
            ),
            actor,
        )

    assert await world.sessions.get(current_session.id) is not None


@time_machine.travel(NOW, tick=False)
async def test_revoke_own_session_raises_not_found_for_unknown_id(
    world: World, make_user: MakeUser
) -> None:
    """Revoking an unknown session id raises SessionNotFoundError."""
    alice = make_user("alice")
    await world.users.add(alice)

    current_session = Session.create(
        user_id=alice.id, token_hash="hash-curr", now=NOW, ttl=TTL
    )
    await world.sessions.add(current_session)

    handler = RevokeOwnSession(world.uow, get_access_guard())
    actor = _make_actor(alice.id)
    unknown_id = uuid.uuid7()

    with pytest.raises(SessionNotFoundError):
        await handler.handle(
            RevokeOwnSessionCommand(
                session_id=unknown_id,
                current_session_id=current_session.id,
            ),
            actor,
        )


@time_machine.travel(NOW, tick=False)
async def test_revoke_own_session_raises_not_found_and_preserves_foreign_session(
    world: World, make_user: MakeUser
) -> None:
    """Revoking another user's session raises SessionNotFoundError (404)."""
    alice = make_user("alice")
    bob = make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)

    alice_session = Session.create(
        user_id=alice.id, token_hash="hash-alice", now=NOW, ttl=TTL
    )
    bob_session = Session.create(
        user_id=bob.id, token_hash="hash-bob", now=NOW, ttl=TTL
    )
    await world.sessions.add(alice_session)
    await world.sessions.add(bob_session)

    handler = RevokeOwnSession(world.uow, get_access_guard())
    actor = _make_actor(alice.id)

    # Review Focus #1: Foreign id looks identical to unknown id (404, never 403)
    with pytest.raises(SessionNotFoundError):
        await handler.handle(
            RevokeOwnSessionCommand(
                session_id=bob_session.id,
                current_session_id=alice_session.id,
            ),
            actor,
        )

    # Bob's session survives untouched
    assert await world.sessions.get(bob_session.id) is not None


@time_machine.travel(NOW, tick=False)
async def test_revoke_other_sessions_deletes_others_and_preserves_current(
    world: World, make_user: MakeUser
) -> None:
    """Revoking other sessions removes all except current for caller."""
    alice = make_user("alice")
    bob = make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)

    current_session = Session.create(
        user_id=alice.id, token_hash="hash-alice-1", now=NOW, ttl=TTL
    )
    other1 = Session.create(
        user_id=alice.id, token_hash="hash-alice-2", now=NOW, ttl=TTL
    )
    other2 = Session.create(
        user_id=alice.id, token_hash="hash-alice-3", now=NOW, ttl=TTL
    )
    bob_session = Session.create(
        user_id=bob.id, token_hash="hash-bob", now=NOW, ttl=TTL
    )

    await world.sessions.add(current_session)
    await world.sessions.add(other1)
    await world.sessions.add(other2)
    await world.sessions.add(bob_session)

    handler = RevokeOtherSessions(world.uow, get_access_guard())
    actor = _make_actor(alice.id)

    with capture_logs() as logs:
        count = await handler.handle(
            RevokeOtherSessionsCommand(current_session_id=current_session.id),
            actor,
        )

    assert count == 2
    assert await world.sessions.get(current_session.id) is not None
    assert await world.sessions.get(other1.id) is None
    assert await world.sessions.get(other2.id) is None
    # Bob's session is untouched
    assert await world.sessions.get(bob_session.id) is not None
    assert world.uow.committed
    assert any(
        log.get("event") == "other sessions revoked"
        and log.get("user_id") == alice.id
        and log.get("count") == 2
        for log in logs
    )
