"""CSV files uploaded once, imported by id on the worker, in turns."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest

from app.modules.transfer.adapters.persistence.unit_of_work import (
    create_in_memory_transfer_uow,
)
from app.modules.transfer.adapters.storage.in_memory_import_files import (
    InMemoryImportFileStore,
)
from app.modules.transfer.application.item_import import (
    IMPORT_PHASES,
    ImportItems,
    InspectItemImport,
    PlanItemImport,
)
from app.modules.transfer.application.stored_imports import (
    ITEM_IMPORTS_JOB,
    DeleteItemImport,
    GetItemImport,
    InspectStoredImportQuery,
    InspectStoredItemImport,
    ItemImportQuery,
    ItemImportView,
    ListItemImports,
    ListItemImportsQuery,
    PlanStoredItemImport,
    PruneItemImports,
    PruneItemImportsCommand,
    QueueItemImport,
    QueueItemImportCommand,
    RecordItemImportProgress,
    RecordItemImportProgressCommand,
    RunQueuedImports,
    RunQueuedImportsCommand,
    StoredImportCommand,
    UploadItemImport,
    UploadItemImportCommand,
)
from app.modules.transfer.domain.bundle import BundleItemType
from app.modules.transfer.domain.errors import (
    ImportFileTooLargeError,
    ImportNotFoundError,
    InvalidImportStateError,
)
from app.modules.transfer.domain.item_import import (
    ImportOptions,
    ImportStatus,
    ItemImport,
)
from app.modules.transfer.domain.tabular import ColumnMapping
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.job_queue import InMemoryJobQueue
from app.shared_kernel.progress import ProgressSnapshot, RecordingProgress

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.transfer.adapters.persistence.in_memory_import_repository import (
        InMemoryItemImportRepository,
    )
    from app.modules.transfer.ports.unit_of_work import TransferUnitOfWork
    from app.shared_kernel.progress import ProgressReporter
    from tests.modules.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)
KEEP = timedelta(hours=24)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "title": "Code",
            "maxLength": 3,
            "x-menagerist": {"kind": "text"},
        }
    },
}
CSV = b"title,code\nAlien #1,A1\nAlien #2,A2\n"
OPTIONS = ImportOptions(
    item_type="signature",
    mapping=(
        ColumnMapping(column="title", target="name"),
        ColumnMapping(column="code", target="code"),
    ),
)
SNAPSHOT = ProgressSnapshot(phases=(), message=None, percent=50, outcome="running")


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    for start in range(0, len(data), 7):
        yield data[start : start + 7]


class World:
    """One instance's imports, files and worker queue, shared by everyone."""

    def __init__(self, shared: Shared) -> None:
        self.shared = shared
        self.repos = shared.transfer_repos
        self.store = InMemoryImportFileStore()
        self.jobs = InMemoryJobQueue()
        self.guard = InMemoryAccessGuard()
        # Accounts the worker can still run imports for.
        self.accounts = {ALICE.id: ALICE, BOB.id: BOB}
        self.reporters: dict[uuid.UUID, RecordingProgress] = {}

    def uow(self) -> TransferUnitOfWork:
        """A unit of work over the shared repositories."""
        return create_in_memory_transfer_uow(self.repos)

    async def give_type(self, actor: Actor) -> None:
        """Give `actor` the item type the files import into."""
        await self.shared.targets(actor).graph.create_item_type(
            BundleItemType(
                ref="signature",
                slug="signature",
                label="Signature",
                attributes_schema=SCHEMA,
            ),
            {},
        )

    async def upload(self, actor: Actor, data: bytes = CSV) -> ItemImport:
        """Upload `data` as `actor`."""
        return await UploadItemImport(self.uow(), self.guard, self.store, KEEP).handle(
            UploadItemImportCommand(
                filename="signed.csv", chunks=_chunks(data), now=NOW
            ),
            actor,
        )

    async def queue(
        self, actor: Actor, item: ItemImport, options: ImportOptions = OPTIONS
    ) -> ItemImportView:
        """Queue `item` as `actor`."""
        return await QueueItemImport(self.uow(), self.guard, self.jobs).handle(
            QueueItemImportCommand(import_id=item.id, options=options, now=NOW),
            actor,
        )

    async def actor_for(
        self, owner_id: uuid.UUID, grants: frozenset[str] | None
    ) -> Actor | None:
        """The account as it is now, as `ImportActors` answers."""
        found = self.accounts.get(owner_id)
        return None if found is None else Actor(id=found.id, roles=found.roles)

    def drain(self) -> RunQueuedImports:
        """The worker's drain over this world."""

        def importer(actor: Actor, progress: ProgressReporter) -> ImportItems:
            targets = self.shared.targets(actor)
            return ImportItems(
                self.uow(), self.guard, targets.presets, targets.graph, progress
            )

        def reporter(import_id: uuid.UUID) -> RecordingProgress:
            return self.reporters.setdefault(import_id, RecordingProgress())

        return RunQueuedImports(
            self.uow, self.guard, self.store, self, importer, reporter
        )

    async def get(self, actor: Actor, item: ItemImport) -> ItemImportView:
        """Read `item` as `actor`."""
        return await GetItemImport(self.repos, self.guard).handle(
            ItemImportQuery(import_id=item.id), actor
        )

    def row(self, item: ItemImport) -> ItemImport:
        """The stored import, as the repository holds it."""
        imports = cast("InMemoryItemImportRepository", self.repos.imports)
        return imports.imports[item.id]


@pytest.fixture
def world(shared: Shared) -> World:
    """A fresh world over the shared repositories."""
    return World(shared)


async def test_an_upload_is_stored_privately_with_its_size(world: World) -> None:
    """The bytes go to the owner's store and the record keeps the size."""
    item = await world.upload(ALICE)
    assert item.size == len(CSV)
    assert item.status is ImportStatus.UPLOADED
    assert item.expires_at == NOW + KEEP
    assert world.store.files[ALICE.id, item.id] == CSV
    assert world.row(item) is item


async def test_an_upload_over_the_limit_keeps_nothing(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The size is checked while the file streams in."""
    from app.modules.transfer.application import stored_imports

    monkeypatch.setattr(stored_imports, "MAX_IMPORT_BYTES", 10)
    with pytest.raises(ImportFileTooLargeError, match="MB limit"):
        await world.upload(ALICE)
    assert not world.store.files
    assert not world.repos.imports.imports  # type: ignore[attr-defined]


async def test_a_failed_record_removes_the_stored_file(world: World) -> None:
    """A file with no record would never be cleaned up."""

    class Broken:
        async def __aenter__(self) -> None:
            raise RuntimeError("database down")

        async def __aexit__(self, *_: object) -> None:
            return None

    upload = UploadItemImport(Broken(), world.guard, world.store, KEEP)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        await upload.handle(
            UploadItemImportCommand(filename="a.csv", chunks=_chunks(CSV), now=NOW),
            ALICE,
        )
    assert not world.store.files


async def test_a_file_is_inspected_and_previewed_by_id(
    world: World, shared: Shared
) -> None:
    """The stored bytes go through the same inspection and preview as an upload."""
    await world.give_type(ALICE)
    item = await world.upload(ALICE)
    targets = shared.targets(ALICE)
    inspection = await InspectStoredItemImport(
        world.repos,
        world.guard,
        world.store,
        InspectItemImport(world.guard, targets.presets, targets.graph),
    ).handle(InspectStoredImportQuery(import_id=item.id, item_type="signature"), ALICE)
    assert inspection.headers == ("title", "code")
    assert inspection.row_count == 2
    plan = await PlanStoredItemImport(
        world.repos,
        world.guard,
        world.store,
        PlanItemImport(world.repos, world.guard, targets.presets, targets.graph),
    ).handle(StoredImportCommand(import_id=item.id, options=OPTIONS), ALICE)
    assert plan.ready
    assert len(plan.entities) == 2


async def test_someone_else_s_file_is_not_found(world: World, shared: Shared) -> None:
    """Even its id tells another person nothing."""
    item = await world.upload(ALICE)
    with pytest.raises(ImportNotFoundError):
        await world.get(BOB, item)
    targets = shared.targets(BOB)
    with pytest.raises(ImportNotFoundError):
        await InspectStoredItemImport(
            world.repos,
            world.guard,
            world.store,
            InspectItemImport(world.guard, targets.presets, targets.graph),
        ).handle(
            InspectStoredImportQuery(import_id=item.id, item_type="signature"), BOB
        )


async def test_a_finished_file_cannot_be_previewed(
    world: World, shared: Shared
) -> None:
    """Its bytes were removed when its import ended."""
    await world.give_type(ALICE)
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    await world.drain().handle(RunQueuedImportsCommand(), SYSTEM_ACTOR)
    targets = shared.targets(ALICE)
    with pytest.raises(InvalidImportStateError, match="no longer stored"):
        await PlanStoredItemImport(
            world.repos,
            world.guard,
            world.store,
            PlanItemImport(world.repos, world.guard, targets.presets, targets.graph),
        ).handle(StoredImportCommand(import_id=item.id, options=OPTIONS), ALICE)


async def test_queueing_asks_the_worker_and_says_who_is_ahead(world: World) -> None:
    """The first in line has nothing ahead; the job is asked for each time."""
    first = await world.upload(ALICE)
    second = await world.upload(ALICE)
    one = await world.queue(ALICE, first)
    two = await world.queue(ALICE, second)
    assert (one.ahead, two.ahead) == (0, 1)
    assert world.row(first).options == OPTIONS
    assert world.jobs.requests == [
        (ITEM_IMPORTS_JOB, ALICE.id),
        (ITEM_IMPORTS_JOB, ALICE.id),
    ]


async def test_queueing_keeps_the_token_ceiling(world: World) -> None:
    """The worker runs the import with no more than the token allowed."""
    item = await world.upload(ALICE)
    token = Actor(id=ALICE.id, roles=ALICE.roles, grants=frozenset({"a", "b"}))
    await world.queue(token, item)
    assert world.row(item).grants == frozenset({"a", "b"})


async def test_a_file_is_queued_once(world: World) -> None:
    """Importing it twice would add its rows twice."""
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    with pytest.raises(InvalidImportStateError):
        await world.queue(ALICE, item)
    assert len(world.jobs.requests) == 1


async def test_the_list_is_the_person_s_own_newest_first(world: World) -> None:
    """Waiting files say how many run before them; the rest say nothing."""
    older = await world.upload(ALICE)
    newer = await world.upload(ALICE)
    await world.upload(BOB)
    await world.queue(ALICE, newer)
    views = await ListItemImports(world.repos, world.guard).handle(
        ListItemImportsQuery(), ALICE
    )
    assert [(v.item.id, v.ahead) for v in views] == [(newer.id, 0), (older.id, None)]


async def test_a_list_with_nothing_waiting_skips_the_queue(world: World) -> None:
    """No place in line is worked out when no file waits."""
    item = await world.upload(ALICE)
    views = await ListItemImports(world.repos, world.guard).handle(
        ListItemImportsQuery(), ALICE
    )
    assert [(v.item.id, v.ahead) for v in views] == [(item.id, None)]


async def test_an_uploaded_file_shows_no_place(world: World) -> None:
    """Only a queued file waits."""
    item = await world.upload(ALICE)
    assert (await world.get(ALICE, item)).ahead is None


async def test_deleting_removes_the_record_and_the_file(world: World) -> None:
    """A queued file leaves the queue too."""
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    await DeleteItemImport(world.uow(), world.guard, world.store).handle(
        ItemImportQuery(import_id=item.id), ALICE
    )
    assert not world.store.files
    with pytest.raises(ImportNotFoundError):
        await world.get(ALICE, item)


async def test_a_running_import_cannot_be_deleted(world: World) -> None:
    """Its rows are being added now."""
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    world.row(item).start(NOW)
    with pytest.raises(InvalidImportStateError, match="being imported"):
        await DeleteItemImport(world.uow(), world.guard, world.store).handle(
            ItemImportQuery(import_id=item.id), ALICE
        )
    assert world.store.files


async def test_the_worker_imports_as_the_owner_and_keeps_the_result(
    world: World, shared: Shared
) -> None:
    """The items are the owner's; the file goes once the import ends."""
    await world.give_type(ALICE)
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    ran = await world.drain().handle(RunQueuedImportsCommand(), SYSTEM_ACTOR)
    assert ran == 1
    done = world.row(item)
    assert done.status is ImportStatus.SUCCEEDED
    assert done.outcome is not None
    assert done.outcome.items_added == 2
    assert not world.store.files
    reporter = world.reporters[item.id]
    assert reporter.calls[0] == ("begin", IMPORT_PHASES)
    assert ("start", "check", 2) in reporter.calls
    assert ("start", "add", 2) in reporter.calls
    assert reporter.calls.count(("advance", 1)) == 4
    assert reporter.calls[-1] == ("done",)
    nodes = shared.graph_repos.nodes._nodes.values()  # type: ignore[attr-defined]
    assert {(n.name, n.owner_id) for n in nodes} == {
        ("Alien #1", ALICE.id),
        ("Alien #2", ALICE.id),
    }


async def test_a_blocked_import_fails_with_the_preview_s_message(
    world: World,
) -> None:
    """The person reads the same reason the preview would have given."""
    await world.give_type(ALICE)
    item = await world.upload(ALICE, b"title,code\nAlien,TOO LONG\n")
    await world.queue(ALICE, item)
    await world.drain().handle(RunQueuedImportsCommand(), SYSTEM_ACTOR)
    failed = world.row(item)
    assert failed.status is ImportStatus.FAILED
    assert failed.failure is not None
    assert "Row 2" in failed.failure
    assert world.reporters[item.id].calls[-1] == ("fail", failed.failure)
    assert not world.store.files


async def test_one_failure_leaves_the_rest_to_run(world: World) -> None:
    """Each import has its own transactions."""
    await world.give_type(ALICE)
    broken = await world.upload(ALICE)
    good = await world.upload(ALICE)
    await world.queue(ALICE, broken, ImportOptions(item_type="missing"))
    await world.queue(ALICE, good)
    assert await world.drain().handle(RunQueuedImportsCommand(), SYSTEM_ACTOR) == 2
    assert world.row(broken).status is ImportStatus.FAILED
    assert world.row(good).status is ImportStatus.SUCCEEDED


async def test_an_import_whose_owner_is_gone_fails(world: World) -> None:
    """A disabled or deleted account imports nothing."""
    item = await world.upload(BOB)
    await world.queue(BOB, item)
    del world.accounts[BOB.id]
    await world.drain().handle(RunQueuedImportsCommand(), SYSTEM_ACTOR)
    assert world.row(item).failure == (
        "The account that queued this import can no longer import."
    )


async def test_an_import_whose_file_is_gone_fails(world: World) -> None:
    """The file may have been removed by hand from the server."""
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    world.store.files.clear()
    await world.drain().handle(RunQueuedImportsCommand(), SYSTEM_ACTOR)
    assert world.row(item).failure == (
        "The uploaded file is no longer stored. Upload it again."
    )


async def test_an_unexpected_error_is_not_shown_to_the_person(world: World) -> None:
    """Only domain messages are written for people."""
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)

    async def boom(owner_id: uuid.UUID, grants: frozenset[str] | None) -> Actor:
        raise RuntimeError("/var/lib/secret/path")

    world.actor_for = boom  # type: ignore[method-assign]
    await world.drain().handle(RunQueuedImportsCommand(), SYSTEM_ACTOR)
    assert world.row(item).failure == "The operation failed unexpectedly."


async def test_an_import_left_running_by_a_stopped_worker_fails(
    world: World,
) -> None:
    """Runs never overlap, so a running import at the start was interrupted."""
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    world.row(item).start(NOW)
    assert await world.drain().handle(RunQueuedImportsCommand(), SYSTEM_ACTOR) == 0
    assert world.row(item).status is ImportStatus.FAILED
    assert world.row(item).failure is not None
    assert "server restarted" in world.row(item).failure  # type: ignore[operator]
    assert not world.store.files


async def test_an_import_deleted_while_running_is_left_gone(world: World) -> None:
    """Finishing an import that no longer exists changes nothing."""
    await world.give_type(ALICE)
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    drain = world.drain()

    async def vanish(owner_id: uuid.UUID, grants: frozenset[str] | None) -> Actor:
        await world.repos.imports.delete(item.id)
        return ALICE

    world.actor_for = vanish  # type: ignore[method-assign]
    await drain.handle(RunQueuedImportsCommand(), SYSTEM_ACTOR)
    assert item.id not in world.repos.imports.imports  # type: ignore[attr-defined]


async def test_progress_is_kept_while_running(world: World) -> None:
    """Each snapshot lands on the import, for its owner to read."""
    item = await world.upload(ALICE)
    await world.queue(ALICE, item)
    world.row(item).start(NOW)
    record = RecordItemImportProgress(world.uow(), world.guard)
    await record.handle(
        RecordItemImportProgressCommand(import_id=item.id, snapshot=SNAPSHOT, now=NOW),
        SYSTEM_ACTOR,
    )
    assert (await world.get(ALICE, item)).item.progress == SNAPSHOT
    await world.repos.imports.delete(item.id)
    await record.handle(
        RecordItemImportProgressCommand(import_id=item.id, snapshot=SNAPSHOT, now=NOW),
        SYSTEM_ACTOR,
    )


async def test_pruning_removes_expired_files_but_not_waiting_ones(
    world: World,
) -> None:
    """A queued or running import is kept until it ends, however old."""
    idle = await world.upload(ALICE)
    waiting = await world.upload(ALICE)
    await world.queue(ALICE, waiting)
    fresh = await world.upload(BOB)
    world.row(fresh).expires_at = NOW + timedelta(days=3)
    removed = await PruneItemImports(world.uow(), world.guard, world.store).handle(
        PruneItemImportsCommand(before=NOW + timedelta(days=2)), SYSTEM_ACTOR
    )
    assert removed == 1
    assert idle.id not in world.repos.imports.imports  # type: ignore[attr-defined]
    assert (ALICE.id, idle.id) not in world.store.files
    assert (ALICE.id, waiting.id) in world.store.files
    found = await world.repos.imports.list_for_owner(scope=ContentFilter.everyone())
    assert {i.id for i in found} == {waiting.id, fresh.id}


async def test_pruning_an_ownerless_import_touches_no_file(world: World) -> None:
    """A row from before accounts has no file of its own to remove."""
    item = await world.upload(ALICE)
    world.row(item).owner_id = None
    removed = await PruneItemImports(world.uow(), world.guard, world.store).handle(
        PruneItemImportsCommand(before=NOW + timedelta(days=2)), SYSTEM_ACTOR
    )
    assert removed == 1
    assert (ALICE.id, item.id) in world.store.files
