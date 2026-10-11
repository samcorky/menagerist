import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.domain.errors import UsernameTakenError
from app.modules.identity.domain.session import Session
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
    await world.sessions.delete_for_user(user_id)
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
