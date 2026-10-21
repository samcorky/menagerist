import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.examples.adapters.persistence.installation_repository import (
    SqlAlchemyInstallationRepository,
)
from app.modules.examples.domain.installation import EntityKind, Installation, Outcome
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

OWNER = uuid.UUID(int=0xA1)


pytestmark = pytest.mark.integration


async def test_round_trips_entities_through_jsonb(db_session: AsyncSession) -> None:
    """Entity records survive the JSONB column unchanged."""
    repo = SqlAlchemyInstallationRepository(db_session)
    installation = Installation.start("demo", OWNER)
    entity_id = uuid.uuid7()
    installation.record(EntityKind.ITEM, "blue", "Blue", entity_id, "h" * 64)
    installation.settle(entity_id, Outcome.KEPT, "edited")
    await repo.add(installation)
    db_session.expire_all()

    stored = await repo.get(installation.id, scope=ContentFilter.everyone())

    assert stored is not None
    record = stored.entities[0]
    assert (record.kind, record.ref, record.label, record.entity_id) == (
        EntityKind.ITEM,
        "blue",
        "Blue",
        entity_id,
    )
    assert (record.content_hash, record.outcome, record.reason) == (
        "h" * 64,
        Outcome.KEPT,
        "edited",
    )


async def test_a_collection_entity_round_trips_through_jsonb(
    db_session: AsyncSession,
) -> None:
    """The `collection` kind is stored and read back."""
    repo = SqlAlchemyInstallationRepository(db_session)
    installation = Installation.start("demo", OWNER)
    entity_id = uuid.uuid7()
    installation.record(EntityKind.COLLECTION, "c", "C", entity_id, "h" * 64)
    await repo.add(installation)
    db_session.expire_all()

    stored = await repo.get(installation.id, scope=ContentFilter.everyone())

    assert stored is not None
    record = stored.entities[0]
    assert (record.kind, record.ref, record.label, record.entity_id) == (
        EntityKind.COLLECTION,
        "c",
        "C",
        entity_id,
    )


async def test_get_returns_none_when_missing(db_session: AsyncSession) -> None:
    """An unknown id yields `None`."""
    repo = SqlAlchemyInstallationRepository(db_session)

    assert await repo.get(uuid.uuid7(), scope=ContentFilter.everyone()) is None


async def test_save_persists_status_changes(db_session: AsyncSession) -> None:
    """Saving writes status and timestamp changes back."""
    repo = SqlAlchemyInstallationRepository(db_session)
    installation = Installation.start("demo", OWNER)
    await repo.add(installation)
    installation.mark_installed()
    await repo.save(installation)
    db_session.expire_all()

    stored = await repo.get(installation.id, scope=ContentFilter.everyone())

    assert stored is not None
    assert stored.installed_at is not None
    assert stored.is_active


async def test_active_lookup_and_list(db_session: AsyncSession) -> None:
    """Only installing or installed rows count as active."""
    repo = SqlAlchemyInstallationRepository(db_session)
    gone = Installation.start("demo", OWNER)
    gone.mark_removed()
    await repo.add(gone)
    live = Installation.start("demo", OWNER)
    await repo.add(live)

    active = await repo.get_active_for_pack("demo", scope=ContentFilter.everyone())

    assert active is not None
    assert active.id == live.id
    assert [i.id for i in await repo.list_active(scope=ContentFilter.everyone())] == [
        live.id
    ]
    assert (
        await repo.get_active_for_pack("other", scope=ContentFilter.everyone()) is None
    )


async def test_the_index_backs_the_one_active_install_rule(
    db_session: AsyncSession,
) -> None:
    """The partial unique index rejects a second active install of one pack."""
    repo = SqlAlchemyInstallationRepository(db_session)
    await repo.add(Installation.start("demo", OWNER))

    with pytest.raises(IntegrityError):
        await repo.add(Installation.start("demo", OWNER))


async def test_list_for_pack_returns_every_status_newest_first(
    db_session: AsyncSession,
) -> None:
    """All of a pack's installations come back, newest first, whatever the status."""
    repo = SqlAlchemyInstallationRepository(db_session)
    first = Installation.start("demo", OWNER)
    first.mark_removed()
    second = Installation.start("demo", OWNER)
    second.mark_failed()
    third = Installation.start("demo", OWNER)
    other = Installation.start("other", OWNER)
    for i in (second, other, first, third):
        await repo.add(i)

    assert [
        i.id for i in await repo.list_for_pack("demo", scope=ContentFilter.everyone())
    ] == [
        third.id,
        second.id,
        first.id,
    ]
    assert await repo.list_for_pack("none", scope=ContentFilter.everyone()) == []
