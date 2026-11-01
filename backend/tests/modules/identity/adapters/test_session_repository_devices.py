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
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import Role, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _user(username: str = "alice") -> User:
    return User.create(
        username=username,
        display_name="Alice",
        password_hash="fake$x",
        role=Role.MEMBER,
        password_expired=False,
        now=NOW,
    )


async def test_session_round_trips_device_fields(db_session: AsyncSession) -> None:
    """Device details round-trip through Postgres via SessionModel."""
    users = SqlAlchemyUserRepository(db_session)
    sessions = SqlAlchemySessionRepository(db_session)

    user = _user()
    await users.add(user)

    session = Session.create(
        user_id=user.id,
        token_hash="dev_hash",
        now=NOW,
        ttl=timedelta(hours=1),
        user_agent="Mozilla/5.0 Firefox/131.0",
        client_ip="192.0.2.1",
        client_platform="Linux",
        client_mobile=False,
    )
    await sessions.add(session)
    db_session.expire_all()

    stored = await sessions.get(session.id)
    assert stored is not None
    assert stored.user_agent == "Mozilla/5.0 Firefox/131.0"
    assert stored.client_ip == "192.0.2.1"
    assert stored.client_platform == "Linux"
    assert stored.client_mobile is False


async def test_session_get_and_unknown_id(db_session: AsyncSession) -> None:
    """A session is found by its id, and an unknown id returns None."""
    users = SqlAlchemyUserRepository(db_session)
    sessions = SqlAlchemySessionRepository(db_session)

    user = _user()
    await users.add(user)

    session = Session.create(
        user_id=user.id,
        token_hash="get_hash",
        now=NOW,
        ttl=timedelta(hours=1),
    )
    await sessions.add(session)
    db_session.expire_all()

    assert await sessions.get(session.id) is not None
    assert await sessions.get(uuid.uuid7()) is None


async def test_session_list_for_user_orders_by_last_seen_and_excludes_expired(
    db_session: AsyncSession,
) -> None:
    """`list_for_user` excludes expired rows and orders newest last_seen_at first."""
    users = SqlAlchemyUserRepository(db_session)
    sessions = SqlAlchemySessionRepository(db_session)

    u1, u2 = _user("user1"), _user("user2")
    await users.add(u1)
    await users.add(u2)

    s_old = Session.create(
        user_id=u1.id, token_hash="old", now=NOW, ttl=timedelta(hours=2)
    )
    s_old.last_seen_at = NOW

    s_new = Session.create(
        user_id=u1.id, token_hash="new", now=NOW, ttl=timedelta(hours=2)
    )
    s_new.last_seen_at = NOW + timedelta(minutes=30)

    s_expired = Session.create(
        user_id=u1.id, token_hash="exp", now=NOW, ttl=timedelta(minutes=10)
    )

    s_other = Session.create(
        user_id=u2.id, token_hash="oth", now=NOW, ttl=timedelta(hours=2)
    )

    for s in (s_old, s_new, s_expired, s_other):
        await sessions.add(s)
    db_session.expire_all()

    check_time = NOW + timedelta(minutes=15)
    listed = await sessions.list_for_user(u1.id, now=check_time)
    assert [s.id for s in listed] == [s_new.id, s_old.id]


async def test_session_list_active_filters_by_user_or_all(
    db_session: AsyncSession,
) -> None:
    """`list_active` returns non-expired sessions, optionally filtered by user_id."""
    users = SqlAlchemyUserRepository(db_session)
    sessions = SqlAlchemySessionRepository(db_session)

    u1, u2 = _user("user1"), _user("user2")
    await users.add(u1)
    await users.add(u2)

    s1 = Session.create(user_id=u1.id, token_hash="s1", now=NOW, ttl=timedelta(hours=1))
    s1.last_seen_at = NOW + timedelta(minutes=10)

    s2 = Session.create(user_id=u2.id, token_hash="s2", now=NOW, ttl=timedelta(hours=1))
    s2.last_seen_at = NOW + timedelta(minutes=20)

    s_exp = Session.create(
        user_id=u1.id, token_hash="exp", now=NOW, ttl=timedelta(minutes=5)
    )

    for s in (s1, s2, s_exp):
        await sessions.add(s)
    db_session.expire_all()

    now = NOW + timedelta(minutes=6)
    all_active = await sessions.list_active(now=now)
    assert [s.id for s in all_active] == [s2.id, s1.id]

    u1_active = await sessions.list_active(now=now, user_id=u1.id)
    assert [s.id for s in u1_active] == [s1.id]

    u2_active = await sessions.list_active(now=now, user_id=u2.id)
    assert [s.id for s in u2_active] == [s2.id]

    unknown_active = await sessions.list_active(now=now, user_id=uuid.uuid7())
    assert unknown_active == []


async def test_session_delete_all_except_preserves_keep_id_and_others(
    db_session: AsyncSession,
) -> None:
    """`delete_all_except` removes other sessions of the target user only."""
    users = SqlAlchemyUserRepository(db_session)
    sessions = SqlAlchemySessionRepository(db_session)

    u1, u2 = _user("user1"), _user("user2")
    await users.add(u1)
    await users.add(u2)

    s_keep = Session.create(
        user_id=u1.id, token_hash="k", now=NOW, ttl=timedelta(hours=1)
    )
    s_drop1 = Session.create(
        user_id=u1.id, token_hash="d1", now=NOW, ttl=timedelta(hours=1)
    )
    s_drop2 = Session.create(
        user_id=u1.id, token_hash="d2", now=NOW, ttl=timedelta(hours=1)
    )
    s_other = Session.create(
        user_id=u2.id, token_hash="o", now=NOW, ttl=timedelta(hours=1)
    )

    for s in (s_keep, s_drop1, s_drop2, s_other):
        await sessions.add(s)
    db_session.expire_all()

    deleted_count = await sessions.delete_all_except(u1.id, s_keep.id)
    assert deleted_count == 2
    assert await sessions.get(s_keep.id) is not None
    assert await sessions.get(s_drop1.id) is None
    assert await sessions.get(s_drop2.id) is None
    assert await sessions.get(s_other.id) is not None
