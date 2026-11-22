"""The transfer unit of work keeps source links only when it commits."""

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.transfer.adapters.persistence.unit_of_work import (
    build_transfer_repos,
    create_transfer_uow,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.source_link import SourceLink
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

OWNER = uuid.UUID(int=0xA1)

pytestmark = pytest.mark.integration


@pytest.fixture
async def session_factory(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions on one connection whose outer transaction is rolled back."""
    engine = create_async_engine(postgres_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        await transaction.rollback()
    await engine.dispose()


def _link(key: str) -> SourceLink:
    return SourceLink.create(
        owner_id=OWNER,
        source="csv:signature:code",
        kind=EntityKind.ITEM,
        key=key,
        entity_id=uuid.uuid7(),
        fields={},
    )


async def _stored(
    session_factory: async_sessionmaker[AsyncSession], key: str
) -> SourceLink | None:
    async with session_factory() as session:
        return await build_transfer_repos(session).links.get_by_key(
            "csv:signature:code", EntityKind.ITEM, key, scope=ContentFilter.of(OWNER)
        )


async def test_a_committed_link_is_kept(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A link added and committed is read back by a fresh session."""
    uow = create_transfer_uow(session_factory)
    async with uow as repos:
        await repos.links.add(_link("A1"))
        await uow.commit()

    assert await _stored(session_factory, "A1") is not None


async def test_a_link_not_committed_is_gone(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A link added without a commit is rolled back."""
    uow = create_transfer_uow(session_factory)
    async with uow as repos:
        await repos.links.add(_link("A2"))

    assert await _stored(session_factory, "A2") is None
