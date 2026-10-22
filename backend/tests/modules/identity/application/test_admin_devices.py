import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine
from structlog.testing import capture_logs

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.authorisation import MEMBER_PERMISSIONS
from app.entrypoints.api.shared.permissions import expand
from app.modules.identity.application.list_sessions import (
    ListSessions,
    ListSessionsQuery,
)
from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.revoke_session import (
    RevokeSession,
    RevokeSessionCommand,
)
from app.modules.identity.domain.errors import CurrentSessionError, SessionNotFoundError
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
TTL = timedelta(hours=24)
IDLE_TIMEOUT = timedelta(hours=2)


def _make_admin_actor(user_id: uuid.UUID | None = None) -> Actor:
    return Actor(
        id=user_id or uuid.uuid7(),
        roles=frozenset({Role.ADMIN.value}),
    )


def _make_member_actor(user_id: uuid.UUID | None = None) -> Actor:
    return Actor(
        id=user_id or uuid.uuid7(),
        roles=frozenset({Role.MEMBER.value}),
    )


def test_session_permissions_catalogue_and_implications() -> None:
    """REVOKE_SESSION implies LIST_SESSIONS and neither is granted to members."""
    assert IdentityPermission.LIST_SESSIONS in expand(
        {IdentityPermission.REVOKE_SESSION}
    )
    assert IdentityPermission.REVOKE_SESSION not in expand(
        {IdentityPermission.LIST_SESSIONS}
    )
    assert IdentityPermission.LIST_SESSIONS not in MEMBER_PERMISSIONS
    assert IdentityPermission.REVOKE_SESSION not in MEMBER_PERMISSIONS


@time_machine.travel(NOW, tick=False)
async def test_list_sessions_forbidden_for_members(
    world: World, make_user: MakeUser
) -> None:
    """Members without identity:session:list cannot list sessions."""
    alice = make_user("alice")
    await world.users.add(alice)

    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    guard = get_access_guard()
    handler = ListSessions(repos, guard, idle_timeout=IDLE_TIMEOUT)

    member_actor = _make_member_actor(alice.id)
    with pytest.raises(ForbiddenError):
        await handler.handle(ListSessionsQuery(), member_actor)


@time_machine.travel(NOW, tick=False)
async def test_revoke_session_forbidden_for_members(
    world: World, make_user: MakeUser
) -> None:
    """Members without identity:session:revoke cannot revoke sessions."""
    alice = make_user("alice")
    await world.users.add(alice)

    guard = get_access_guard()
    handler = RevokeSession(world.uow, guard)

    member_actor = _make_member_actor(alice.id)
    with pytest.raises(ForbiddenError):
        await handler.handle(
            RevokeSessionCommand(
                session_id=uuid.uuid7(),
                current_session_id=uuid.uuid7(),
            ),
            member_actor,
        )


@time_machine.travel(NOW, tick=False)
async def test_list_sessions_returns_all_active_sessions_with_user_details(
    world: World, make_user: MakeUser
) -> None:
    """Administrators see active sessions across all users, newest first."""
    alice = make_user("alice", display_name="Alice Smith")
    bob = make_user("bob", display_name="Bob Jones")
    await world.users.add(alice)
    await world.users.add(bob)

    s_alice = Session.create(
        user_id=alice.id,
        token_hash="hash-alice",
        now=NOW - timedelta(hours=2),
        ttl=TTL,
        user_agent="Firefox on Linux",
        client_ip="192.0.2.1",
    )
    s_alice.seen(NOW - timedelta(minutes=30))

    s_alice_second = Session.create(
        user_id=alice.id,
        token_hash="hash-alice-2",
        now=NOW - timedelta(hours=1, minutes=30),
        ttl=TTL,
        user_agent="Firefox on Mobile",
        client_ip="192.0.2.1",
    )
    s_alice_second.seen(NOW - timedelta(minutes=15))

    s_bob = Session.create(
        user_id=bob.id,
        token_hash="hash-bob",
        now=NOW - timedelta(hours=1),
        ttl=TTL,
        user_agent="Chrome on Windows",
        client_ip="192.0.2.2",
    )
    s_bob.seen(NOW - timedelta(minutes=5))

    s_orphaned = Session.create(
        user_id=uuid.uuid7(),
        token_hash="hash-orphan",
        now=NOW - timedelta(hours=1),
        ttl=TTL,
    )

    await world.sessions.add(s_alice)
    await world.sessions.add(s_alice_second)
    await world.sessions.add(s_bob)
    await world.sessions.add(s_orphaned)

    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    guard = get_access_guard()
    handler = ListSessions(repos, guard, idle_timeout=IDLE_TIMEOUT)

    admin_actor = _make_admin_actor()
    results = await handler.handle(ListSessionsQuery(), admin_actor)

    assert len(results) == 3
    # Newest last_seen_at first: Bob (5m), Alice2 (15m), Alice1 (30m)
    assert results[0].session.id == s_bob.id
    assert results[0].username == "bob"
    assert results[0].display_name == "Bob Jones"

    assert results[1].session.id == s_alice_second.id
    assert results[1].username == "alice"
    assert results[1].display_name == "Alice Smith"

    assert results[2].session.id == s_alice.id
    assert results[2].username == "alice"
    assert results[2].display_name == "Alice Smith"


@time_machine.travel(NOW, tick=False)
async def test_list_sessions_excludes_expired_and_idle_sessions(
    world: World, make_user: MakeUser
) -> None:
    """Expired or idle sessions are excluded from the listing."""
    alice = make_user("alice")
    await world.users.add(alice)

    active = Session.create(
        user_id=alice.id,
        token_hash="hash-active",
        now=NOW - timedelta(minutes=30),
        ttl=TTL,
    )
    active.seen(NOW - timedelta(minutes=5))

    expired = Session.create(
        user_id=alice.id,
        token_hash="hash-expired",
        now=NOW - timedelta(days=2),
        ttl=timedelta(hours=1),
    )

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
    guard = get_access_guard()
    handler = ListSessions(repos, guard, idle_timeout=IDLE_TIMEOUT)

    admin_actor = _make_admin_actor()
    results = await handler.handle(ListSessionsQuery(), admin_actor)

    assert len(results) == 1
    assert results[0].session.id == active.id


@time_machine.travel(NOW, tick=False)
async def test_list_sessions_filters_by_user_id(
    world: World, make_user: MakeUser
) -> None:
    """Passing user_id filters sessions to only that user."""
    alice = make_user("alice")
    bob = make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)

    s_alice = Session.create(
        user_id=alice.id, token_hash="hash-alice", now=NOW, ttl=TTL
    )
    s_bob = Session.create(user_id=bob.id, token_hash="hash-bob", now=NOW, ttl=TTL)
    await world.sessions.add(s_alice)
    await world.sessions.add(s_bob)

    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    guard = get_access_guard()
    handler = ListSessions(repos, guard, idle_timeout=IDLE_TIMEOUT)

    admin_actor = _make_admin_actor()
    results = await handler.handle(ListSessionsQuery(user_id=alice.id), admin_actor)

    assert len(results) == 1
    assert results[0].session.id == s_alice.id
    assert results[0].username == "alice"


@time_machine.travel(NOW, tick=False)
async def test_list_sessions_unknown_user_id_returns_empty_list(
    world: World, make_user: MakeUser
) -> None:
    """An unknown user_id returns an empty list, not 404 (Review Focus #5)."""
    alice = make_user("alice")
    await world.users.add(alice)

    s_alice = Session.create(
        user_id=alice.id, token_hash="hash-alice", now=NOW, ttl=TTL
    )
    await world.sessions.add(s_alice)

    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    guard = get_access_guard()
    handler = ListSessions(repos, guard, idle_timeout=IDLE_TIMEOUT)

    admin_actor = _make_admin_actor()
    unknown_id = uuid.uuid7()
    results = await handler.handle(ListSessionsQuery(user_id=unknown_id), admin_actor)

    assert results == []


@time_machine.travel(NOW, tick=False)
async def test_revoke_session_success_and_logs(
    world: World, make_user: MakeUser
) -> None:
    """Administrator revokes another user's session, deleting it and logging."""
    alice = make_user("alice")
    admin = make_user("admin", role=Role.ADMIN)
    await world.users.add(alice)
    await world.users.add(admin)

    admin_session = Session.create(
        user_id=admin.id, token_hash="hash-admin", now=NOW, ttl=TTL
    )
    alice_session1 = Session.create(
        user_id=alice.id, token_hash="hash-alice-1", now=NOW, ttl=TTL
    )
    alice_session2 = Session.create(
        user_id=alice.id, token_hash="hash-alice-2", now=NOW, ttl=TTL
    )
    await world.sessions.add(admin_session)
    await world.sessions.add(alice_session1)
    await world.sessions.add(alice_session2)

    guard = get_access_guard()
    handler = RevokeSession(world.uow, guard)
    admin_actor = _make_admin_actor(admin.id)

    with capture_logs() as logs:
        await handler.handle(
            RevokeSessionCommand(
                session_id=alice_session1.id,
                current_session_id=admin_session.id,
            ),
            admin_actor,
        )

    assert await world.sessions.get(alice_session1.id) is None
    assert await world.sessions.get(alice_session2.id) is not None
    assert await world.sessions.get(admin_session.id) is not None
    assert world.uow.committed
    assert any(
        log.get("event") == "session revoked"
        and log.get("session_id") == alice_session1.id
        and log.get("user_id") == alice.id
        and log.get("revoked_by") == admin.id
        for log in logs
    )


@time_machine.travel(NOW, tick=False)
async def test_revoke_session_refuses_current_session(
    world: World, make_user: MakeUser
) -> None:
    """Administrator revoking current session raises CurrentSessionError (409)."""
    admin = make_user("admin", role=Role.ADMIN)
    await world.users.add(admin)

    admin_session = Session.create(
        user_id=admin.id, token_hash="hash-admin", now=NOW, ttl=TTL
    )
    await world.sessions.add(admin_session)

    guard = get_access_guard()
    handler = RevokeSession(world.uow, guard)
    admin_actor = _make_admin_actor(admin.id)

    # Review Focus #2: Current session cannot be revoked through devices route
    with pytest.raises(CurrentSessionError, match="Cannot revoke the current session"):
        await handler.handle(
            RevokeSessionCommand(
                session_id=admin_session.id,
                current_session_id=admin_session.id,
            ),
            admin_actor,
        )

    assert await world.sessions.get(admin_session.id) is not None


@time_machine.travel(NOW, tick=False)
async def test_revoke_session_raises_not_found_for_unknown_id(
    world: World, make_user: MakeUser
) -> None:
    """Revoking an unknown session id raises SessionNotFoundError (404)."""
    admin = make_user("admin", role=Role.ADMIN)
    await world.users.add(admin)

    admin_session = Session.create(
        user_id=admin.id, token_hash="hash-admin", now=NOW, ttl=TTL
    )
    await world.sessions.add(admin_session)

    guard = get_access_guard()
    handler = RevokeSession(world.uow, guard)
    admin_actor = _make_admin_actor(admin.id)
    unknown_id = uuid.uuid7()

    with pytest.raises(SessionNotFoundError):
        await handler.handle(
            RevokeSessionCommand(
                session_id=unknown_id,
                current_session_id=admin_session.id,
            ),
            admin_actor,
        )
