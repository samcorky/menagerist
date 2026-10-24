"""Installations are visible to their owner only, in memory and on Postgres."""

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.adapters.persistence.installation_repository import (
    SqlAlchemyInstallationRepository,
)
from app.modules.examples.domain.installation import Installation
from app.modules.examples.ports.installation_repository import InstallationRepository  # noqa: TC001
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ALICE = uuid.UUID(int=0xA1)
BOB = uuid.UUID(int=0xB2)


async def _check_scope(repo: InstallationRepository) -> None:
    mine = Installation.start("demo", ALICE)
    theirs = Installation.start("demo", BOB)
    removed = Installation.start("demo", BOB)
    removed.mark_removed()
    for installation in (mine, theirs, removed):
        await repo.add(installation)
    alice, bob, everyone = (
        ContentFilter.of(ALICE),
        ContentFilter.of(BOB),
        ContentFilter.everyone(),
    )

    assert await repo.get(mine.id, scope=alice) is not None
    assert await repo.get(mine.id, scope=bob) is None
    assert (await repo.get(theirs.id, scope=everyone)) is not None
    active = await repo.get_active_for_pack("demo", scope=alice)
    assert active is not None
    assert active.owner_id == ALICE
    other = await repo.get_active_for_pack("demo", scope=bob)
    assert other is not None
    assert other.id == theirs.id
    assert (
        await repo.get_active_for_pack("demo", scope=ContentFilter.of(uuid.uuid7()))
        is None
    )
    assert [i.id for i in await repo.list_active(scope=alice)] == [mine.id]
    assert [i.id for i in await repo.list_active(scope=bob)] == [theirs.id]
    assert len(await repo.list_active(scope=everyone)) == 2
    assert [i.id for i in await repo.list_for_pack("demo", scope=bob)] == [
        removed.id,
        theirs.id,
    ]
    assert len(await repo.list_for_pack("demo", scope=everyone)) == 3
    assert (await repo.get_active_for_pack("demo", scope=everyone)) is not None


async def test_in_memory_installations_are_scoped_by_owner() -> None:
    """Get, active lookup and both lists only return the scope's installations."""
    await _check_scope(InMemoryInstallationRepository())


@pytest.mark.integration
async def test_postgres_installations_are_scoped_by_owner(
    db_session: AsyncSession,
) -> None:
    """The same rules hold in SQL."""
    await _check_scope(SqlAlchemyInstallationRepository(db_session))


@pytest.mark.integration
async def test_owner_round_trips_and_legacy_rows_are_invisible_to_a_person(
    db_session: AsyncSession,
) -> None:
    """A stored owner comes back; a row with no owner matches only everyone."""
    repo = SqlAlchemyInstallationRepository(db_session)
    mine = Installation.start("demo", ALICE)
    legacy = Installation.start("legacy", ALICE)
    legacy.owner_id = None
    await repo.add(mine)
    await repo.add(legacy)
    db_session.expire_all()

    stored = await repo.get(mine.id, scope=ContentFilter.of(ALICE))
    assert stored is not None
    assert stored.owner_id == ALICE
    assert await repo.get(legacy.id, scope=ContentFilter.of(ALICE)) is None
    seen = await repo.get(legacy.id, scope=ContentFilter.everyone())
    assert seen is not None
    assert seen.owner_id is None


@pytest.mark.integration
async def test_two_people_may_hold_the_same_pack_but_one_person_may_not(
    db_session: AsyncSession,
) -> None:
    """The unique index is per pack and owner among active installations."""
    repo = SqlAlchemyInstallationRepository(db_session)
    await repo.add(Installation.start("demo", ALICE))
    await repo.add(Installation.start("demo", BOB))

    with pytest.raises(IntegrityError):
        await repo.add(Installation.start("demo", ALICE))
