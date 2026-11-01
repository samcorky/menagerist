import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.domain.errors import UsernameTakenError
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.throttle import (
    AttemptWindow,
    ThrottleKey,
    ThrottleKind,
)
from app.modules.identity.domain.user import Role

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


async def test_user_add_get_and_lookup(world: World, make_user: MakeUser) -> None:
    """Users are found by id and by case-insensitive username."""
    user = make_user("Alice")
    await world.users.add(user)
    assert await world.users.get(user.id) is user
    assert await world.users.get_by_username("ALICE") is user
    assert await world.users.get(uuid.uuid7()) is None
    assert await world.users.get_by_username("nobody") is None


async def test_user_add_rejects_duplicate_username(
    world: World, make_user: MakeUser
) -> None:
    """Usernames are unique regardless of case."""
    await world.users.add(make_user("alice"))
    with pytest.raises(UsernameTakenError):
        await world.users.add(make_user("Alice"))


async def test_user_save_list_and_counts(world: World, make_user: MakeUser) -> None:
    """Saved changes show; counts cover everyone and enabled admins only."""
    admin = make_user("admin", role=Role.ADMIN)
    gone = make_user("gone", role=Role.ADMIN)
    member = make_user("member")
    for user in (admin, gone, member):
        await world.users.add(user)
    gone.disable()
    await world.users.save(gone)

    assert await world.users.count() == 3
    assert await world.users.count_admins() == 1
    listed = await world.users.list_all()
    assert [u.id for u in listed] == sorted(u.id for u in (admin, gone, member))


async def test_session_lookup_and_delete(world: World) -> None:
    """Sessions are found by token hash and removed by id."""
    session = Session.create(
        user_id=uuid.uuid7(), token_hash="h1", now=NOW, ttl=timedelta(hours=1)
    )
    await world.sessions.add(session)
    assert await world.sessions.get_by_token_hash("h1") is session
    assert await world.sessions.get_by_token_hash("nope") is None
    await world.sessions.delete(session.id)
    assert await world.sessions.get_by_token_hash("h1") is None
    await world.sessions.delete(session.id)


async def test_session_delete_for_user_and_expired(world: World) -> None:
    """A user's sessions go together; expired ones are swept."""
    user_id = uuid.uuid7()
    mine = [
        Session.create(
            user_id=user_id, token_hash=f"m{i}", now=NOW, ttl=timedelta(hours=1)
        )
        for i in range(2)
    ]
    other = Session.create(
        user_id=uuid.uuid7(), token_hash="o", now=NOW, ttl=timedelta(hours=1)
    )
    stale = Session.create(
        user_id=uuid.uuid7(), token_hash="s", now=NOW, ttl=timedelta(minutes=1)
    )
    for s in (*mine, other, stale):
        await world.sessions.add(s)

    assert await world.sessions.delete_expired(NOW + timedelta(minutes=2)) == 1
    assert await world.sessions.get_by_token_hash("s") is None
    assert await world.sessions.delete_for_user(user_id) == 2
    assert await world.sessions.delete_for_user(user_id) == 0
    assert await world.sessions.get_by_token_hash("m0") is None
    assert await world.sessions.get_by_token_hash("o") is other


async def test_session_save_and_raw_token_misses(world: World) -> None:
    """Saved changes show, and only the hash finds a session, never the token."""
    session = Session.create(
        user_id=uuid.uuid7(), token_hash="hashed", now=NOW, ttl=timedelta(hours=1)
    )
    await world.sessions.add(session)
    later = NOW + timedelta(minutes=5)
    session.last_seen_at = later
    await world.sessions.save(session)
    stored = await world.sessions.get_by_token_hash("hashed")
    assert stored is not None
    assert stored.last_seen_at == later
    assert await world.sessions.get_by_token_hash("raw-token") is None


async def test_session_get_by_id(world: World) -> None:
    """Sessions are retrieved by their row id; unknown ids give None."""
    session = Session.create(
        user_id=uuid.uuid7(), token_hash="h1", now=NOW, ttl=timedelta(hours=1)
    )
    await world.sessions.add(session)
    assert await world.sessions.get(session.id) is session
    assert await world.sessions.get(uuid.uuid7()) is None


async def test_session_list_for_user_orders_by_last_seen_and_excludes_expired(
    world: World,
) -> None:
    """`list_for_user` excludes expired rows and orders newest last_seen_at first."""
    user_id = uuid.uuid7()
    other_user_id = uuid.uuid7()

    s_old = Session.create(
        user_id=user_id, token_hash="old", now=NOW, ttl=timedelta(hours=2)
    )
    s_old.last_seen_at = NOW

    s_new = Session.create(
        user_id=user_id, token_hash="new", now=NOW, ttl=timedelta(hours=2)
    )
    s_new.last_seen_at = NOW + timedelta(minutes=30)

    s_expired = Session.create(
        user_id=user_id, token_hash="exp", now=NOW, ttl=timedelta(minutes=10)
    )

    s_other = Session.create(
        user_id=other_user_id, token_hash="oth", now=NOW, ttl=timedelta(hours=2)
    )

    for s in (s_old, s_new, s_expired, s_other):
        await world.sessions.add(s)

    check_time = NOW + timedelta(minutes=15)
    listed = await world.sessions.list_for_user(user_id, now=check_time)
    assert listed == [s_new, s_old]


async def test_session_list_active_filters_by_user_or_all(world: World) -> None:
    """`list_active` returns non-expired sessions, optionally filtered by user_id."""
    u1, u2 = uuid.uuid7(), uuid.uuid7()
    s1 = Session.create(user_id=u1, token_hash="s1", now=NOW, ttl=timedelta(hours=1))
    s1.last_seen_at = NOW + timedelta(minutes=10)

    s2 = Session.create(user_id=u2, token_hash="s2", now=NOW, ttl=timedelta(hours=1))
    s2.last_seen_at = NOW + timedelta(minutes=20)

    s_exp = Session.create(
        user_id=u1, token_hash="exp", now=NOW, ttl=timedelta(minutes=5)
    )

    for s in (s1, s2, s_exp):
        await world.sessions.add(s)

    now = NOW + timedelta(minutes=6)
    all_active = await world.sessions.list_active(now=now)
    assert all_active == [s2, s1]

    u1_active = await world.sessions.list_active(now=now, user_id=u1)
    assert u1_active == [s1]

    u2_active = await world.sessions.list_active(now=now, user_id=u2)
    assert u2_active == [s2]

    unknown_active = await world.sessions.list_active(now=now, user_id=uuid.uuid7())
    assert unknown_active == []


async def test_session_delete_all_except_preserves_keep_id_and_others(
    world: World,
) -> None:
    """`delete_all_except` removes other sessions of the target user only."""
    user_id = uuid.uuid7()
    other_user = uuid.uuid7()

    s_keep = Session.create(
        user_id=user_id, token_hash="k", now=NOW, ttl=timedelta(hours=1)
    )
    s_drop1 = Session.create(
        user_id=user_id, token_hash="d1", now=NOW, ttl=timedelta(hours=1)
    )
    s_drop2 = Session.create(
        user_id=user_id, token_hash="d2", now=NOW, ttl=timedelta(hours=1)
    )
    s_other = Session.create(
        user_id=other_user, token_hash="o", now=NOW, ttl=timedelta(hours=1)
    )

    for s in (s_keep, s_drop1, s_drop2, s_other):
        await world.sessions.add(s)

    deleted_count = await world.sessions.delete_all_except(user_id, s_keep.id)
    assert deleted_count == 2
    assert await world.sessions.get(s_keep.id) is s_keep
    assert await world.sessions.get(s_drop1.id) is None
    assert await world.sessions.get(s_drop2.id) is None
    assert await world.sessions.get(s_other.id) is s_other


async def test_for_update_lookup_matches_plain_lookup(
    world: World, make_user: MakeUser
) -> None:
    """The locking lookup finds users case-insensitively and misses unknowns."""
    user = make_user("Alice")
    await world.users.add(user)
    assert await world.users.get_by_username_for_update("ALICE") is user
    assert await world.users.get_by_username_for_update("bob") is None


async def test_get_for_update_matches_get(world: World, make_user: MakeUser) -> None:
    """The locking id lookup finds users and misses unknown ids."""
    user = make_user("alice")
    await world.users.add(user)
    assert await world.users.get_for_update(user.id) is user
    assert await world.users.get_for_update(uuid.uuid7()) is None


async def test_setup_lock_and_locking_admin_count(
    world: World, make_user: MakeUser
) -> None:
    """The in-memory twins match the plain count and the lock is a no-op."""
    await world.users.lock_for_setup()
    await world.users.add(make_user("root", role=Role.ADMIN))
    await world.users.add(make_user("member"))
    await world.users.lock_admin_changes()
    assert await world.users.count_admins() == 1


async def test_attempt_release_gives_one_back_and_ignores_unknown_keys(
    world: World,
) -> None:
    """A release lowers the count of its own window and does nothing otherwise."""
    key = ThrottleKey(kind=ThrottleKind.USERNAME, digest="k" * 64)
    window = timedelta(minutes=15)
    for _ in range(3):
        await world.attempts.record_failure(key, limit=2, window=window, now=NOW)

    await world.attempts.release_attempt(key, window_start=NOW, limit=2)
    await world.attempts.release_attempt(key, window_start=NOW, limit=2)
    await world.attempts.release_attempt(
        ThrottleKey(kind=ThrottleKind.IP, digest="x" * 64), window_start=NOW, limit=2
    )

    assert world.attempts.windows[key] == AttemptWindow(count=1, window_start=NOW)
    assert list(world.attempts.windows) == [key]
