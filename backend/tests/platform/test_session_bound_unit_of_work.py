"""One session shared by several units of work: a single commit, a single rollback."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.identity.adapters.persistence.models import UserModel
from app.modules.identity.adapters.persistence.unit_of_work import (
    create_identity_uow_on_session,
)
from app.modules.identity.domain.user import User

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def factory(postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A committing session factory; empties the users table afterwards."""
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(UserModel))
        await engine.dispose()


def _user(name: str) -> User:
    return User.create(
        username=name,
        display_name=name,
        password_hash="x",
        now=datetime.now(UTC),
    )


async def _add_then_fail(uow: IdentityUnitOfWork) -> None:
    async with uow as repos:
        await repos.users.add(_user("lost"))
        raise RuntimeError("boom")


async def _count(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as session:
        return (
            await session.execute(select(func.count()).select_from(UserModel))
        ).scalar_one()


async def test_commit_happens_once_on_the_shared_session(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Work in two entries of the unit is only visible after its commit."""
    callbacks: list[str] = []

    async def called() -> None:
        callbacks.append("done")

    async with factory() as session:
        uow = create_identity_uow_on_session(session)
        async with uow as repos:
            await repos.users.add(_user("first"))
        async with uow as repos:
            await repos.users.add(_user("second"))
            assert await _count(factory) == 0
            uow.on_commit(called)
            await uow.commit()

    assert await _count(factory) == 2
    assert callbacks == ["done"]


async def test_an_error_rolls_back_everything_and_leaves_the_session_open(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """The unit rolls back on error but the session stays usable for its owner."""
    async with factory() as session:
        uow = create_identity_uow_on_session(session)
        with pytest.raises(RuntimeError, match="boom"):
            await _add_then_fail(uow)
        async with uow as repos:
            assert await repos.users.count() == 0

    assert await _count(factory) == 0
