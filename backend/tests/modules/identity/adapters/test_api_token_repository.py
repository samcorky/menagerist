import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.modules.identity.adapters.persistence.api_token_repository import (
    SqlAlchemyApiTokenRepository,
)
from app.modules.identity.adapters.persistence.in_memory_api_token_repository import (
    InMemoryApiTokenRepository,
)
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.domain.api_token import ApiToken
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.api_token_repository import ApiTokenRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


@dataclass
class Harness:
    """A repository plus a way to make users that exist for its foreign keys."""

    repo: ApiTokenRepository
    new_user: Callable[[], Awaitable[uuid.UUID]]
    refresh: Callable[[], None]


@pytest.fixture
def memory_harness() -> Harness:
    """The in-memory adapter."""

    async def _new_user() -> uuid.UUID:
        return uuid.uuid7()

    return Harness(InMemoryApiTokenRepository(), _new_user, lambda: None)


@pytest.fixture
def sql_harness(db_session: AsyncSession) -> Harness:
    """The SQLAlchemy adapter over a rolled-back transaction."""
    users = SqlAlchemyUserRepository(db_session)

    async def _new_user() -> uuid.UUID:
        user = User.create(
            username=f"user-{uuid.uuid4().hex[:8]}",
            display_name="User",
            password_hash="fake$x",
            role=Role.MEMBER,
            password_expired=False,
            now=NOW,
        )
        await users.add(user)
        return user.id

    return Harness(
        SqlAlchemyApiTokenRepository(db_session), _new_user, db_session.expire_all
    )


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
def harness(request: pytest.FixtureRequest) -> Harness:
    """The same cases run against both adapters."""
    harness: Harness = request.getfixturevalue(f"{request.param}_harness")
    return harness


def _token(
    user_id: uuid.UUID,
    *,
    created: datetime = NOW,
    expires: datetime | None = None,
    grants: tuple[str, ...] = ("graph:item:read",),
) -> ApiToken:
    return ApiToken.create(
        token_id=uuid.uuid7(),
        user_id=user_id,
        name="Script",
        secret_hash=uuid.uuid4().hex * 2,
        grants=grants,
        now=created,
        expires_at=expires or created + timedelta(days=30),
    )


async def test_add_then_get_round_trips_every_field(harness: Harness) -> None:
    """Every field, including grants and last use, survives storage."""
    user_id = await harness.new_user()
    token = _token(user_id, grants=("graph:item:read", "graph:item:write"))
    token.used(NOW + timedelta(minutes=2))
    await harness.repo.add(token)
    harness.refresh()

    stored = await harness.repo.get(token.id)
    assert stored is not None
    assert stored.id == token.id
    assert stored.user_id == user_id
    assert stored.name == "Script"
    assert stored.secret_hash == token.secret_hash
    assert stored.grants == frozenset({"graph:item:read", "graph:item:write"})
    assert stored.created_at == token.created_at
    assert stored.expires_at == token.expires_at
    assert stored.last_used_at == NOW + timedelta(minutes=2)


async def test_get_unknown_id_is_none(harness: Harness) -> None:
    """An unknown id finds nothing."""
    assert await harness.repo.get(uuid.uuid7()) is None


async def test_list_hides_expired_orders_newest_first_and_scopes_to_user(
    harness: Harness,
) -> None:
    """Only the user's unexpired tokens come back, newest created first."""
    user_id = await harness.new_user()
    other_id = await harness.new_user()
    older = _token(user_id, created=NOW - timedelta(days=2))
    newer = _token(user_id, created=NOW - timedelta(days=1))
    expired = _token(
        user_id,
        created=NOW - timedelta(days=10),
        expires=NOW - timedelta(seconds=1),
    )
    foreign = _token(other_id)
    for token in (older, expired, newer, foreign):
        await harness.repo.add(token)

    listed = await harness.repo.list_for_user(user_id, now=NOW)
    assert [t.id for t in listed] == [newer.id, older.id]
    assert await harness.repo.count_active(user_id, now=NOW) == 2
    assert await harness.repo.count_active(other_id, now=NOW) == 1


async def test_equal_created_at_lists_by_id(harness: Harness) -> None:
    """Ties on `created_at` break by id, the same in both adapters."""
    user_id = await harness.new_user()
    tokens = [_token(user_id) for _ in range(4)]
    for token in reversed(tokens):
        await harness.repo.add(token)

    listed = await harness.repo.list_for_user(user_id, now=NOW)
    assert [t.id for t in listed] == sorted(t.id for t in tokens)


async def test_changes_to_a_returned_token_need_save(harness: Harness) -> None:
    """Mutating an added or fetched token changes nothing until `save`."""
    user_id = await harness.new_user()
    token = _token(user_id)
    await harness.repo.add(token)
    token.used(NOW)

    fetched = await harness.repo.get(token.id)
    assert fetched is not None
    assert fetched.last_used_at is None
    fetched.used(NOW)
    listed = (await harness.repo.list_for_user(user_id, now=NOW))[0]
    assert listed.last_used_at is None


async def test_expiry_instant_is_inactive(harness: Harness) -> None:
    """A token is not active at its expiry instant."""
    user_id = await harness.new_user()
    token = _token(user_id, expires=NOW + timedelta(hours=1))
    await harness.repo.add(token)
    at_expiry = token.expires_at
    assert await harness.repo.count_active(user_id, now=at_expiry) == 0
    assert await harness.repo.list_for_user(user_id, now=at_expiry) == []


async def test_delete_removes_one_and_ignores_unknown(harness: Harness) -> None:
    """Deleting an unknown id is a no-op; a known id goes."""
    user_id = await harness.new_user()
    keep, drop = _token(user_id), _token(user_id)
    await harness.repo.add(keep)
    await harness.repo.add(drop)

    await harness.repo.delete(uuid.uuid7())
    await harness.repo.delete(drop.id)

    assert await harness.repo.get(drop.id) is None
    assert await harness.repo.get(keep.id) is not None


async def test_delete_for_user_counts_and_spares_others(harness: Harness) -> None:
    """Only the named user's tokens go, and the count says how many."""
    user_id = await harness.new_user()
    other_id = await harness.new_user()
    await harness.repo.add(_token(user_id))
    await harness.repo.add(_token(user_id))
    spared = _token(other_id)
    await harness.repo.add(spared)

    assert await harness.repo.delete_for_user(user_id) == 2
    assert await harness.repo.delete_for_user(user_id) == 0
    assert await harness.repo.get(spared.id) is not None


async def test_delete_expired_removes_only_expired(harness: Harness) -> None:
    """Expired tokens go; live ones stay."""
    user_id = await harness.new_user()
    expired = _token(
        user_id, created=NOW - timedelta(days=5), expires=NOW - timedelta(days=1)
    )
    live = _token(user_id)
    await harness.repo.add(expired)
    await harness.repo.add(live)

    assert await harness.repo.delete_expired(NOW) == 1
    assert await harness.repo.get(expired.id) is None
    assert await harness.repo.get(live.id) is not None


async def test_save_persists_last_used_at(harness: Harness) -> None:
    """`save` writes a change made after `add`."""
    user_id = await harness.new_user()
    token = _token(user_id)
    await harness.repo.add(token)
    token.used(NOW + timedelta(minutes=1))
    await harness.repo.save(token)
    harness.refresh()

    stored = await harness.repo.get(token.id)
    assert stored is not None
    assert stored.last_used_at == NOW + timedelta(minutes=1)


@pytest.mark.integration
async def test_tokens_cascade_with_their_user(db_session: AsyncSession) -> None:
    """Deleting a user removes their tokens."""
    users = SqlAlchemyUserRepository(db_session)
    repo = SqlAlchemyApiTokenRepository(db_session)
    user = User.create(
        username="cascade",
        display_name="Cascade",
        password_hash="fake$x",
        role=Role.MEMBER,
        password_expired=False,
        now=NOW,
    )
    await users.add(user)
    token = _token(user.id)
    await repo.add(token)

    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    db_session.expire_all()

    assert await repo.get(token.id) is None
