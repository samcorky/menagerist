"""The scheduled purge removes expired sessions and API tokens, and nothing else."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.application.purge_expired_credentials import (
    PurgeExpiredCredentials,
    PurgeExpiredCredentialsCommand,
)
from app.modules.identity.domain.api_token import ApiToken
from app.modules.identity.domain.session import Session
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
TTL = timedelta(hours=1)


def _token(user_id: uuid.UUID, *, expires_at: datetime) -> ApiToken:
    return ApiToken.create(
        token_id=uuid.uuid7(),
        user_id=user_id,
        name="ci",
        secret_hash=f"hash-{uuid.uuid7()}",
        grants=["graph:node:read"],
        now=NOW - timedelta(days=100),
        expires_at=expires_at,
    )


async def test_it_removes_only_expired_sessions_and_tokens(
    world: World, make_user: MakeUser
) -> None:
    """Live credentials survive; the count reports what went."""
    user = make_user("alice")
    await world.users.add(user)
    await world.sessions.add(
        Session.create(user_id=user.id, token_hash="old", now=NOW - 2 * TTL, ttl=TTL)
    )
    await world.sessions.add(
        Session.create(user_id=user.id, token_hash="live", now=NOW, ttl=TTL)
    )
    old = _token(user.id, expires_at=NOW - timedelta(days=1))
    live = _token(user.id, expires_at=NOW + timedelta(days=1))
    await world.tokens.add(old)
    await world.tokens.add(live)

    result = await PurgeExpiredCredentials(world.uow, get_access_guard()).handle(
        PurgeExpiredCredentialsCommand(now=NOW), SYSTEM_ACTOR
    )

    assert (result.sessions, result.tokens) == (1, 1)
    assert await world.sessions.get_by_token_hash("old") is None
    assert await world.sessions.get_by_token_hash("live") is not None
    assert world.uow.committed is True


async def test_an_empty_store_purges_nothing(world: World) -> None:
    """Nothing expired is not an error."""
    result = await PurgeExpiredCredentials(world.uow, get_access_guard()).handle(
        PurgeExpiredCredentialsCommand(now=NOW), SYSTEM_ACTOR
    )
    assert (result.sessions, result.tokens) == (0, 0)


async def test_only_the_system_may_purge(world: World) -> None:
    """A signed-in member is refused."""
    member = Actor(id=uuid.uuid7(), roles=frozenset({"member"}))
    with pytest.raises(ForbiddenError):
        await PurgeExpiredCredentials(world.uow, get_access_guard()).handle(
            PurgeExpiredCredentialsCommand(now=NOW), member
        )
