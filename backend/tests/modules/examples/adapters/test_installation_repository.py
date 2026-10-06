import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.examples.adapters.persistence.installation_repository import (
    SqlAlchemyInstallationRepository,
)
from app.modules.examples.domain.installation import EntityKind, Installation, Outcome

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_round_trips_entities_through_jsonb(db_session: AsyncSession) -> None:
    """Entity records survive the JSONB column unchanged."""
    repo = SqlAlchemyInstallationRepository(db_session)
    installation = Installation.start("demo")
    entity_id = uuid.uuid7()
    installation.record(EntityKind.ITEM, "blue", "Blue", entity_id, "h" * 64)
    installation.settle(entity_id, Outcome.KEPT, "edited")
    await repo.add(installation)
    db_session.expire_all()

    stored = await repo.get(installation.id)

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


async def test_get_returns_none_when_missing(db_session: AsyncSession) -> None:
    """An unknown id yields `None`."""
    repo = SqlAlchemyInstallationRepository(db_session)

    assert await repo.get(uuid.uuid7()) is None


async def test_save_persists_status_changes(db_session: AsyncSession) -> None:
    """Saving writes status and timestamp changes back."""
    repo = SqlAlchemyInstallationRepository(db_session)
    installation = Installation.start("demo")
    await repo.add(installation)
    installation.mark_installed()
    await repo.save(installation)
    db_session.expire_all()

    stored = await repo.get(installation.id)

    assert stored is not None
    assert stored.installed_at is not None
    assert stored.is_active


async def test_active_lookup_and_list(db_session: AsyncSession) -> None:
    """Only installing or installed rows count as active."""
    repo = SqlAlchemyInstallationRepository(db_session)
    gone = Installation.start("demo")
    gone.mark_removed()
    await repo.add(gone)
    live = Installation.start("demo")
    await repo.add(live)

    active = await repo.get_active_for_pack("demo")

    assert active is not None
    assert active.id == live.id
    assert [i.id for i in await repo.list_active()] == [live.id]
    assert await repo.get_active_for_pack("other") is None


async def test_the_index_backs_the_one_active_install_rule(
    db_session: AsyncSession,
) -> None:
    """The partial unique index rejects a second active install of one pack."""
    repo = SqlAlchemyInstallationRepository(db_session)
    await repo.add(Installation.start("demo"))

    with pytest.raises(IntegrityError):
        await repo.add(Installation.start("demo"))
