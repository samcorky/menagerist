"""The Postgres import repository, and how it stores an import's options."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.transfer.adapters.persistence.import_repository import (
    SqlAlchemyItemImportRepository,
    options_from_json,
    options_to_json,
)
from app.modules.transfer.domain.bundle import NameLookup
from app.modules.transfer.domain.item_import import (
    ImportOptions,
    ImportOutcome,
    ImportStatus,
    ItemImport,
)
from app.modules.transfer.domain.tabular import (
    ColumnMapping,
    ConnectionColumn,
    ConnectionEnd,
    DayMonthOrder,
    ExtraField,
    ExtraFieldKind,
)
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.progress import PhaseState, ProgressSnapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ALICE = uuid.UUID(int=0xA1)
BOB = uuid.UUID(int=0xB2)
NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)
OPTIONS = ImportOptions(
    item_type="signature",
    mapping=(
        ColumnMapping(column="title", target="name"),
        ColumnMapping(
            column="paper",
            target=None,
            extra=ExtraField(key="paper", title="Paper", kind=ExtraFieldKind.CHOICE),
        ),
    ),
    list_separator=";",
    day_month_order=DayMonthOrder.MONTH_FIRST,
    key_field="name",
    restore=("A14",),
    connections=(
        ConnectionColumn(
            column="signer",
            relationship_type="signed",
            item_type="person",
            row_end=ConnectionEnd.TARGET,
            on_missing=NameLookup.SKIP,
        ),
    ),
)
SNAPSHOT = ProgressSnapshot(
    phases=(
        PhaseState(
            key="check", label="Checking rows", state="running", done=3, total=9
        ),
    ),
    message=None,
    percent=12,
    outcome="running",
)


def _upload(owner: uuid.UUID = ALICE) -> ItemImport:
    return ItemImport.upload(
        owner_id=owner,
        filename="a.csv",
        size=5_000_000_000,
        now=NOW,
        keep_for=timedelta(hours=24),
    )


def test_options_survive_being_stored() -> None:
    """Every option, including kept fields and connections, reads back the same."""
    assert options_from_json(options_to_json(OPTIONS)) == OPTIONS


@pytest.mark.integration
async def test_an_import_round_trips_with_everything_it_holds(
    db_session: AsyncSession,
) -> None:
    """Options, grants, progress and outcome are stored and read back."""
    repo = SqlAlchemyItemImportRepository(db_session)
    item = _upload()
    await repo.add(item)
    item.queue(OPTIONS, frozenset({"b", "a"}), NOW)
    item.start(NOW)
    item.report(SNAPSHOT, NOW)
    item.succeed(ImportOutcome(items_added=4, connections_added=2), NOW)
    await repo.save(item)
    found = await repo.get(item.id, scope=ContentFilter.of(ALICE))
    assert found is not None
    assert found.options == OPTIONS
    assert found.grants == frozenset({"a", "b"})
    assert found.progress == SNAPSHOT
    assert found.outcome == ImportOutcome(items_added=4, connections_added=2)
    assert found.size == 5_000_000_000
    assert await repo.get(item.id, scope=ContentFilter.of(BOB)) is None


@pytest.mark.integration
async def test_queries_scope_order_and_expire(db_session: AsyncSession) -> None:
    """The person's list, the queue, who went last and what expired."""
    repo = SqlAlchemyItemImportRepository(db_session)
    first, second, bobs = _upload(), _upload(), _upload(BOB)
    for item in (first, second, bobs):
        await repo.add(item)
    bobs.queue(OPTIONS, None, NOW - timedelta(minutes=1))
    second.queue(OPTIONS, None, NOW)
    first.queue(OPTIONS, None, NOW)
    first.start(NOW)
    for item in (first, second, bobs):
        await repo.save(item)
    own = await repo.list_for_owner(scope=ContentFilter.of(ALICE))
    assert [i.id for i in own] == [second.id, first.id]
    queued = await repo.list_with_status(ImportStatus.QUEUED)
    assert [i.id for i in queued] == [bobs.id, second.id]
    assert await repo.recent_owners(5) == [ALICE]
    expired = await repo.list_expired(NOW + timedelta(days=2))
    assert {i.id for i in expired} == {first.id, second.id, bobs.id}
    await repo.delete(first.id)
    assert await repo.get(first.id, scope=ContentFilter.everyone()) is None
