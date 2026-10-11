import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.adapters.persistence.session_repository import (
    SqlAlchemySessionRepository,
)
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.domain.errors import UsernameTakenError
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import Role, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _user(username: str = "alice", role: Role = Role.MEMBER) -> User:
    return User.create(
        username=username,
        display_name="Alice",
        password_hash="fake$x",
        role=role,
        password_expired=True,
        now=NOW,
    )


async def test_user_round_trips_every_field(db_session: AsyncSession) -> None:
    """A stored user reads back with all its fields, including lockout state."""
    repo = SqlAlchemyUserRepository(db_session)
    user = _user("Alice", Role.ADMIN)
    for _ in range(5):
        user.record_failure(NOW)
    user.disable()
    await repo.add(user)
    db_session.expire_all()

    stored = await repo.get(user.id)

    assert stored is not None
    assert (stored.username, stored.display_name, stored.password_hash) == (
        "alice",
        "Alice",
        "fake$x",
    )
    assert (stored.role, stored.password_expired, stored.disabled) == (
        Role.ADMIN,
        True,
        True,
    )
    assert stored.failed_attempts == 5
    assert stored.locked_until == user.locked_until
    assert stored.failure_window_started_at == NOW
    assert (stored.created_at, stored.updated_at) == (user.created_at, user.updated_at)


async def test_user_lookup_is_case_insensitive(db_session: AsyncSession) -> None:
    """Username lookup ignores case; unknown ids and names give `None`."""
    repo = SqlAlchemyUserRepository(db_session)
    user = _user()
    await repo.add(user)
    found = await repo.get_by_username("ALICE")
    assert found is not None
    assert found.id == user.id
    assert await repo.get_by_username("bob") is None
    assert await repo.get(uuid.uuid7()) is None


async def test_duplicate_username_conflicts_case_insensitively(
    db_session: AsyncSession,
) -> None:
    """A second user whose username differs only in case is rejected."""
    repo = SqlAlchemyUserRepository(db_session)
    await repo.add(_user("alice"))
    with pytest.raises(UsernameTakenError):
        await repo.add(_user("Alice"))
    assert await repo.count() == 1


async def test_save_updates_and_counts(db_session: AsyncSession) -> None:
    """Saved changes persist; counts include everyone and enabled admins only."""
    repo = SqlAlchemyUserRepository(db_session)
    admin, gone, member = (
        _user("admin", Role.ADMIN),
        _user("gone", Role.ADMIN),
        _user("member"),
    )
    for user in (admin, gone, member):
        await repo.add(user)
    gone.disable()
    await repo.save(gone)
    db_session.expire_all()

    reloaded = await repo.get(gone.id)
    assert reloaded is not None
    assert reloaded.disabled is True
    assert await repo.count() == 3
    assert await repo.count_admins() == 1
    assert [u.id for u in await repo.list_all()] == sorted(
        u.id for u in (admin, gone, member)
    )


async def test_session_lookup_and_delete(db_session: AsyncSession) -> None:
    """Sessions are found by token hash and removed by id."""
    users = SqlAlchemyUserRepository(db_session)
    repo = SqlAlchemySessionRepository(db_session)
    user = _user()
    await users.add(user)
    session = Session.create(
        user_id=user.id, token_hash="a" * 64, now=NOW, ttl=timedelta(hours=1)
    )
    await repo.add(session)
    db_session.expire_all()

    stored = await repo.get_by_token_hash("a" * 64)
    assert stored is not None
    assert (stored.id, stored.user_id) == (session.id, user.id)
    assert (stored.created_at, stored.expires_at, stored.last_seen_at) == (
        session.created_at,
        session.expires_at,
        session.last_seen_at,
    )
    assert await repo.get_by_token_hash("b" * 64) is None
    await repo.delete(session.id)
    assert await repo.get_by_token_hash("a" * 64) is None


async def test_session_delete_for_user_and_expired(db_session: AsyncSession) -> None:
    """A user's sessions go together; expired ones are swept."""
    users = SqlAlchemyUserRepository(db_session)
    repo = SqlAlchemySessionRepository(db_session)
    alice, bob = _user("alice"), _user("bob")
    await users.add(alice)
    await users.add(bob)
    long = timedelta(hours=1)
    for token, owner, ttl in (
        ("a1", alice, long),
        ("a2", alice, long),
        ("b1", bob, long),
        ("stale", bob, timedelta(minutes=1)),
    ):
        await repo.add(
            Session.create(user_id=owner.id, token_hash=token, now=NOW, ttl=ttl)
        )

    assert await repo.delete_expired(NOW + timedelta(minutes=2)) == 1
    assert await repo.get_by_token_hash("stale") is None
    await repo.delete_for_user(alice.id)
    assert await repo.get_by_token_hash("a1") is None
    assert await repo.get_by_token_hash("a2") is None
    assert await repo.get_by_token_hash("b1") is not None


async def test_session_save_and_raw_token_misses(db_session: AsyncSession) -> None:
    """Saved changes persist, and a raw token never matches a stored hash."""
    users = SqlAlchemyUserRepository(db_session)
    repo = SqlAlchemySessionRepository(db_session)
    user = _user()
    await users.add(user)
    token = "raw-token"
    session = Session.create(
        user_id=user.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        now=NOW,
        ttl=timedelta(hours=1),
    )
    await repo.add(session)
    later = NOW + timedelta(minutes=5)
    session.last_seen_at = later
    await repo.save(session)
    db_session.expire_all()

    stored = await repo.get_by_token_hash(session.token_hash)
    assert stored is not None
    assert stored.last_seen_at == later
    assert await repo.get_by_token_hash(token) is None


async def test_for_update_lookup_matches_plain_lookup(db_session: AsyncSession) -> None:
    """The locking lookup finds users case-insensitively and misses unknowns."""
    repo = SqlAlchemyUserRepository(db_session)
    user = _user()
    await repo.add(user)
    found = await repo.get_by_username_for_update("ALICE")
    assert found is not None
    assert found.id == user.id
    assert await repo.get_by_username_for_update("bob") is None


async def test_get_for_update_matches_get(db_session: AsyncSession) -> None:
    """The locking id lookup finds users and misses unknown ids."""
    repo = SqlAlchemyUserRepository(db_session)
    user = _user()
    await repo.add(user)
    found = await repo.get_for_update(user.id)
    assert found is not None
    assert found.username == "alice"
    assert await repo.get_for_update(uuid.uuid7()) is None


async def test_setup_lock_and_locking_admin_count(db_session: AsyncSession) -> None:
    """The advisory lock is taken and the locking count counts enabled admins."""
    repo = SqlAlchemyUserRepository(db_session)
    await repo.add(_user("root", Role.ADMIN))
    gone = _user("gone", Role.ADMIN)
    gone.disable()
    await repo.add(gone)
    await repo.add(_user("member"))

    await repo.lock_for_setup()

    await repo.lock_admin_changes()
    assert await repo.count_admins() == 1
