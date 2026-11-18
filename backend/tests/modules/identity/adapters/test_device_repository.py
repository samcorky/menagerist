"""SqlAlchemyDeviceRepository against Postgres, and the sessions that link to it."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import update

from app.modules.identity.adapters.persistence.device_repository import (
    SqlAlchemyDeviceRepository,
)
from app.modules.identity.adapters.persistence.models import DeviceModel, SessionModel
from app.modules.identity.adapters.persistence.session_repository import (
    SqlAlchemySessionRepository,
)
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.domain.device import Device
from app.modules.identity.domain.session import DisplayMode, Session
from app.modules.identity.domain.user import Role, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
TTL = timedelta(days=365)


async def _user(db_session: AsyncSession, username: str = "alice") -> User:
    user = User.create(
        username=username,
        display_name=username.title(),
        password_hash="fake$x",
        role=Role.MEMBER,
        password_expired=False,
        now=NOW,
    )
    await SqlAlchemyUserRepository(db_session).add(user)
    return user


def _device(user: User, token_hash: str, *, now: datetime = NOW) -> Device:
    return Device.create(
        user_id=user.id,
        token_hash=token_hash,
        now=now,
        ttl=TTL,
        user_agent="Firefox",
        platform="Linux",
        mobile=False,
        display_mode=DisplayMode.STANDALONE,
    )


async def test_device_round_trips_and_is_found_by_hash(
    db_session: AsyncSession,
) -> None:
    """A device is stored, changed and found by id and by its cookie's hash."""
    devices = SqlAlchemyDeviceRepository(db_session)
    user = await _user(db_session)
    device = _device(user, "hash-1")
    await devices.add(device)
    device.seen(NOW + timedelta(days=1), ttl=TTL, user_agent="Firefox 2")
    device.rename("Sam's laptop")
    await devices.save(device)
    db_session.expire_all()

    stored = await devices.get_by_token_hash("hash-1")
    assert stored is not None
    assert stored.id == device.id
    assert stored.user_agent == "Firefox 2"
    assert stored.platform is None
    assert stored.name == "Sam's laptop"
    assert stored.display_mode is DisplayMode.STANDALONE
    assert stored.last_seen_at == NOW + timedelta(days=1)
    assert (await devices.get(device.id)) is not None
    assert await devices.get(uuid.uuid7()) is None
    assert await devices.get_by_token_hash("missing") is None


async def test_device_deletes(db_session: AsyncSession) -> None:
    """Delete one, a user's except one, and the expired ones."""
    devices = SqlAlchemyDeviceRepository(db_session)
    alice = await _user(db_session)
    bob = await _user(db_session, "bob")
    kept, dropped, old = (
        _device(alice, "a1"),
        _device(alice, "a2"),
        _device(alice, "a3", now=NOW - TTL * 2),
    )
    bobs, gone = _device(bob, "b1"), _device(bob, "b2")
    for device in (kept, dropped, old, bobs, gone):
        await devices.add(device)

    await devices.delete(gone.id)
    assert await devices.delete_expired(NOW) == 1
    assert await devices.delete_for_user(alice.id, keep_id=kept.id) == 1

    assert [d.id for d in await devices.list_for_user(alice.id)] == [kept.id]
    assert [d.id for d in await devices.list_for_user(bob.id)] == [bobs.id]
    assert await devices.delete_for_user(bob.id) == 1


async def test_sessions_link_to_their_device(db_session: AsyncSession) -> None:
    """A session keeps its device and display mode; both go with the device."""
    devices = SqlAlchemyDeviceRepository(db_session)
    sessions = SqlAlchemySessionRepository(db_session)
    user = await _user(db_session)
    device = _device(user, "hash-1")
    await devices.add(device)
    linked = Session.create(
        user_id=user.id,
        token_hash="s1",
        now=NOW,
        ttl=timedelta(hours=1),
        device_id=device.id,
        display_mode=DisplayMode.STANDALONE,
    )
    loose = Session.create(
        user_id=user.id, token_hash="s2", now=NOW, ttl=timedelta(hours=1)
    )
    await sessions.add(linked)
    await sessions.add(loose)
    db_session.expire_all()

    stored = await sessions.get(linked.id)
    assert stored is not None
    assert stored.device_id == device.id
    assert stored.display_mode is DisplayMode.STANDALONE
    assert await sessions.delete_for_device(device.id) == 1
    assert await sessions.get(loose.id) is not None


async def test_an_unknown_stored_display_mode_reads_as_none(
    db_session: AsyncSession,
) -> None:
    """A value written by a newer version is not an error, just unknown."""
    sessions = SqlAlchemySessionRepository(db_session)
    user = await _user(db_session)
    session = Session.create(
        user_id=user.id, token_hash="s1", now=NOW, ttl=timedelta(hours=1)
    )
    await sessions.add(session)
    await db_session.execute(
        update(SessionModel)
        .where(SessionModel.id == session.id)
        .values(display_mode="fullscreen")
    )
    db_session.expire_all()

    stored = await sessions.get(session.id)
    assert stored is not None
    assert stored.display_mode is None


async def test_deleting_a_device_cascades_to_its_sessions(
    db_session: AsyncSession,
) -> None:
    """The foreign key removes a forgotten device's sessions too."""
    devices = SqlAlchemyDeviceRepository(db_session)
    sessions = SqlAlchemySessionRepository(db_session)
    user = await _user(db_session)
    device = _device(user, "hash-1")
    await devices.add(device)
    session = Session.create(
        user_id=user.id,
        token_hash="s1",
        now=NOW,
        ttl=timedelta(hours=1),
        device_id=device.id,
    )
    await sessions.add(session)

    await devices.delete(device.id)
    db_session.expire_all()

    assert await sessions.get(session.id) is None


async def test_an_unknown_stored_device_display_mode_reads_as_none(
    db_session: AsyncSession,
) -> None:
    """A value written by a newer version is not an error, just unknown."""
    devices = SqlAlchemyDeviceRepository(db_session)
    user = await _user(db_session)
    device = _device(user, "hash-unknown")
    await devices.add(device)
    await db_session.execute(
        update(DeviceModel)
        .where(DeviceModel.id == device.id)
        .values(display_mode="fullscreen")
    )
    db_session.expire_all()

    stored = await devices.get(device.id)
    assert stored is not None
    assert stored.display_mode is None
