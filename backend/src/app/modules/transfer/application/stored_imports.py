"""Import a CSV that is uploaded once: inspect, preview and run it by id.

The run happens on the worker. Queueing records the options on the import and asks
for the `transfer.item_imports` job, whose run works through every queued import,
one at a time and in turns between people, each as its owner.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.transfer.application.item_import import (
    InspectItemImport,
    ItemImportInspection,
    ItemImportRequest,
    PlanItemImport,
)
from app.modules.transfer.application.permissions import TransferPermission
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import (
    ImportNotFoundError,
    InvalidImportStateError,
)
from app.modules.transfer.domain.item_import import (
    ImportOptions,
    ImportOutcome,
    ImportStatus,
    ItemImport,
    turn_order,
)
from app.modules.transfer.domain.tabular import MAX_IMPORT_BYTES
from app.modules.transfer.ports.unit_of_work import TransferRepos, TransferUnitOfWork
from app.shared_kernel.access import Access, Requires, System
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import CommandHandler, QueryHandler, UseCase
from app.shared_kernel.paging import (
    Page,
    SearchedPagedQuery,
    SortOrder,
    page_rows,
    timestamp_value,
)
from app.shared_kernel.progress import ProgressSnapshot, failure_reason
from app.shared_kernel.text import matches_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.transfer.application.item_import import ImportItems
    from app.modules.transfer.domain.plan import Plan
    from app.modules.transfer.ports.import_actors import ImportActors
    from app.modules.transfer.ports.import_file_store import ImportFileStore
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.job_queue import JobQueue
    from app.shared_kernel.progress import ProgressReporter

logger = structlog.get_logger()

ITEM_IMPORTS_JOB = "transfer.item_imports"
# How far back whose turn it was is remembered, for taking turns.
_SERVED_MEMORY = 50
_INTERRUPTED = (
    "The import stopped part-way, because the server restarted. Run it again."
)
_OWNER_GONE = "The account that queued this import can no longer import."
_FILE_GONE = "The uploaded file is no longer stored. Upload it again."
_ACCESS = Requires(TransferPermission.BUNDLE_IMPORT)


def import_request(options: ImportOptions, data: bytes) -> ItemImportRequest:
    """The request the CSV import reads, for a stored file and its options."""
    return ItemImportRequest(
        data=data,
        item_type=options.item_type,
        mapping=options.mapping,
        list_separator=options.list_separator,
        day_month_order=options.day_month_order,
        key_field=options.key_field,
        restore=options.restore,
        connections=options.connections,
    )


@dataclass(frozen=True, kw_only=True)
class ItemImportView:
    """An import and, while it waits, how many imports will run before it."""

    item: ItemImport
    ahead: int | None


def _own(actor: Actor) -> ContentFilter:
    # Even an administrator sees only their own uploads: they hold personal data.
    return ContentFilter.of(actor.id)


async def _owned(
    repos: TransferRepos, import_id: uuid.UUID, actor: Actor
) -> ItemImport:
    item = await repos.imports.get(import_id, scope=_own(actor))
    if item is None:
        raise ImportNotFoundError(f"You have no uploaded file {import_id}.")
    return item


async def _places(repos: TransferRepos) -> dict[uuid.UUID, int]:
    """How many imports run before each waiting one."""
    waiting = await repos.imports.list_with_status(ImportStatus.QUEUED)
    served = await repos.imports.recent_owners(_SERVED_MEMORY)
    running = len(await repos.imports.list_with_status(ImportStatus.RUNNING))
    return {
        item.id: running + place
        for place, item in enumerate(turn_order(waiting, served))
    }


async def _view(repos: TransferRepos, item: ItemImport) -> ItemImportView:
    if item.status is not ImportStatus.QUEUED:
        return ItemImportView(item=item, ahead=None)
    return ItemImportView(item=item, ahead=(await _places(repos)).get(item.id, 0))


@dataclass(frozen=True, kw_only=True, eq=False)
class UploadItemImportCommand:
    """A CSV file arriving as a stream of bytes."""

    filename: str
    chunks: AsyncIterator[bytes]
    now: datetime


class UploadItemImport(
    CommandHandler[TransferUnitOfWork, UploadItemImportCommand, ItemImport]
):
    """Store an uploaded file for the person to inspect, preview and import.

    Raises:
        ImportFileTooLargeError: the file is over the size limit.
    """

    access: ClassVar[Access] = _ACCESS

    def __init__(
        self,
        uow: TransferUnitOfWork,
        guard: AccessGuard,
        store: ImportFileStore,
        keep_for: timedelta,
    ) -> None:
        """Initialise with the unit of work, the file store and how long to keep."""
        super().__init__(uow, guard)
        self._store = store
        self._keep_for = keep_for

    async def _handle(
        self, request: UploadItemImportCommand, actor: Actor
    ) -> ItemImport:
        """Store the bytes, then record the file."""
        item = ItemImport.upload(
            owner_id=actor.id,
            filename=request.filename,
            size=0,
            now=request.now,
            keep_for=self._keep_for,
        )
        item.size = await self._store.put(
            actor.id, item.id, request.chunks, max_bytes=MAX_IMPORT_BYTES
        )
        try:
            async with self._uow as repos:
                await repos.imports.add(item)
                await self._uow.commit()
        except BaseException:
            await self._store.delete(actor.id, item.id)
            raise
        return item


@dataclass(frozen=True, kw_only=True)
class ItemImportQuery:
    """One of the person's uploaded files."""

    import_id: uuid.UUID


class ItemImportSort(StrEnum):
    """What a person's uploaded files can be sorted by: fields of the response."""

    CREATED_AT = "created_at"
    FILENAME = "filename"
    SIZE = "size"
    STATUS = "status"
    FINISHED_AT = "finished_at"
    EXPIRES_AT = "expires_at"


@dataclass(kw_only=True)
class ListItemImportsQuery(SearchedPagedQuery[ItemImportSort]):
    """The files the person has uploaded and not removed, newest first unless told."""

    order: SortOrder = SortOrder.DESC


class GetItemImport(QueryHandler[TransferRepos, ItemImportQuery, ItemImportView]):
    """Return an uploaded file, its progress and its result.

    Raises:
        ImportNotFoundError: the person has no such file.
    """

    access: ClassVar[Access] = _ACCESS

    async def _handle(self, request: ItemImportQuery, actor: Actor) -> ItemImportView:
        """Read the import, with its place in the queue while it waits."""
        return await _view(
            self._repos, await _owned(self._repos, request.import_id, actor)
        )


class ListItemImports(
    QueryHandler[TransferRepos, ListItemImportsQuery, Page[ItemImportView]]
):
    """Return the person's uploaded files, newest first."""

    access: ClassVar[Access] = _ACCESS

    async def _handle(
        self, request: ListItemImportsQuery, actor: Actor
    ) -> Page[ItemImportView]:
        """Read a page of the imports, each waiting one with its place in the queue."""
        items = await self._repos.imports.list_for_owner(scope=_own(actor))
        places = (
            await _places(self._repos)
            if any(i.status is ImportStatus.QUEUED for i in items)
            else {}
        )
        views = [ItemImportView(item=i, ahead=places.get(i.id)) for i in items]
        return page_rows(
            [view for view in views if matches_text(request.q, view.item.filename)],
            request.page_request(ItemImportSort.CREATED_AT),
            id_of=lambda view: view.item.id,
            values={
                ItemImportSort.CREATED_AT: lambda v: timestamp_value(v.item.created_at),
                ItemImportSort.FILENAME: lambda view: view.item.filename.lower(),
                ItemImportSort.SIZE: lambda view: view.item.size,
                ItemImportSort.STATUS: lambda view: str(view.item.status),
                ItemImportSort.FINISHED_AT: lambda v: (
                    None
                    if v.item.finished_at is None
                    else timestamp_value(v.item.finished_at)
                ),
                ItemImportSort.EXPIRES_AT: lambda v: timestamp_value(v.item.expires_at),
            },
        )


class DeleteItemImport(CommandHandler[TransferUnitOfWork, ItemImportQuery, None]):
    """Remove an uploaded file; a queued one is taken out of the queue.

    Raises:
        ImportNotFoundError: the person has no such file.
        InvalidImportStateError: it is being imported now.
    """

    access: ClassVar[Access] = _ACCESS

    def __init__(
        self, uow: TransferUnitOfWork, guard: AccessGuard, store: ImportFileStore
    ) -> None:
        """Initialise with the unit of work and the file store."""
        super().__init__(uow, guard)
        self._store = store

    async def _handle(self, request: ItemImportQuery, actor: Actor) -> None:
        """Delete the record, then the file."""
        async with self._uow as repos:
            item = await _owned(repos, request.import_id, actor)
            if item.status is ImportStatus.RUNNING:
                raise InvalidImportStateError(
                    "This file is being imported now, so it cannot be removed."
                )
            await repos.imports.delete(item.id)
            await self._uow.commit()
        await self._store.delete(actor.id, item.id)


async def _stored_file(
    repos: TransferRepos, store: ImportFileStore, import_id: uuid.UUID, actor: Actor
) -> bytes:
    item = await _owned(repos, import_id, actor)
    data = None if item.is_finished else await store.read(actor.id, item.id)
    if data is None:
        raise InvalidImportStateError(_FILE_GONE)
    return data


@dataclass(frozen=True, kw_only=True)
class InspectStoredImportQuery:
    """An uploaded file and the item type it would become."""

    import_id: uuid.UUID
    item_type: str


class InspectStoredItemImport(
    QueryHandler[TransferRepos, InspectStoredImportQuery, ItemImportInspection]
):
    """`InspectItemImport` for an uploaded file.

    Raises:
        ImportNotFoundError: the person has no such file.
        InvalidImportStateError: the file is no longer stored.
        ValidationError: as `InspectItemImport`.
    """

    access: ClassVar[Access] = _ACCESS

    def __init__(
        self,
        repos: TransferRepos,
        guard: AccessGuard,
        store: ImportFileStore,
        inspect: InspectItemImport,
    ) -> None:
        """Initialise with the repositories, the file store and the inspection."""
        super().__init__(repos, guard)
        self._store = store
        self._inspect = inspect

    async def _handle(
        self, request: InspectStoredImportQuery, actor: Actor
    ) -> ItemImportInspection:
        """Read the stored file and inspect it."""
        data = await _stored_file(self._repos, self._store, request.import_id, actor)
        return await self._inspect.handle(
            ItemImportRequest(data=data, item_type=request.item_type), actor
        )


@dataclass(frozen=True, kw_only=True)
class StoredImportCommand:
    """An uploaded file and how to import it."""

    import_id: uuid.UUID
    options: ImportOptions


class PlanStoredItemImport(QueryHandler[TransferRepos, StoredImportCommand, "Plan"]):
    """`PlanItemImport` for an uploaded file.

    Raises:
        ImportNotFoundError: the person has no such file.
        InvalidImportStateError: the file is no longer stored.
        ValidationError: as `PlanItemImport`.
    """

    access: ClassVar[Access] = _ACCESS

    def __init__(
        self,
        repos: TransferRepos,
        guard: AccessGuard,
        store: ImportFileStore,
        plan: PlanItemImport,
    ) -> None:
        """Initialise with the repositories, the file store and the preview."""
        super().__init__(repos, guard)
        self._store = store
        self._plan = plan

    async def _handle(self, request: StoredImportCommand, actor: Actor) -> Plan:
        """Read the stored file and preview it."""
        data = await _stored_file(self._repos, self._store, request.import_id, actor)
        return await self._plan.handle(import_request(request.options, data), actor)


@dataclass(frozen=True, kw_only=True)
class QueueItemImportCommand:
    """An uploaded file to import with `options`."""

    import_id: uuid.UUID
    options: ImportOptions
    now: datetime


class QueueItemImport(
    CommandHandler[TransferUnitOfWork, QueueItemImportCommand, ItemImportView]
):
    """Queue an uploaded file for the worker to import.

    The worker plans it again as it starts, so a problem found then (a value that
    cannot be imported, an item type since deleted) fails the import with the
    preview's message.

    Raises:
        ImportNotFoundError: the person has no such file.
        InvalidImportStateError: it is queued, running or finished already.
    """

    access: ClassVar[Access] = _ACCESS

    def __init__(
        self, uow: TransferUnitOfWork, guard: AccessGuard, jobs: JobQueue
    ) -> None:
        """Initialise with the unit of work and the worker's queue."""
        super().__init__(uow, guard)
        self._jobs = jobs

    async def _handle(
        self, request: QueueItemImportCommand, actor: Actor
    ) -> ItemImportView:
        """Record the options, then ask the worker to run its queue."""
        async with self._uow as repos:
            item = await _owned(repos, request.import_id, actor)
            item.queue(request.options, actor.grants, request.now)
            await repos.imports.save(item)
            view = await _view(repos, item)
            await self._uow.commit()
        # After the commit, so the run finds the import; a lost request leaves it
        # queued for the next run, which any later request or Run now starts.
        await self._jobs.request(ITEM_IMPORTS_JOB, requested_by=actor.id)
        return view


@dataclass(frozen=True, kw_only=True)
class RecordItemImportProgressCommand:
    """How far a running import has got."""

    import_id: uuid.UUID
    snapshot: ProgressSnapshot
    now: datetime


class RecordItemImportProgress(
    CommandHandler[TransferUnitOfWork, RecordItemImportProgressCommand, None]
):
    """Keep a running import's progress, for its owner to watch."""

    access: ClassVar[Access] = System()

    async def _handle(
        self, request: RecordItemImportProgressCommand, actor: Actor
    ) -> None:
        """Store the snapshot on the import, if it is still there."""
        async with self._uow as repos:
            item = await repos.imports.get(
                request.import_id, scope=ContentFilter.everyone()
            )
            if item is None:
                return
            item.report(request.snapshot, request.now)
            await repos.imports.save(item)
            await self._uow.commit()


@dataclass(frozen=True, kw_only=True)
class RunQueuedImportsCommand:
    """Work through the queue until nothing is waiting."""


type ImporterFactory = Callable[[Actor, ProgressReporter], ImportItems]


class RunQueuedImports(UseCase[RunQueuedImportsCommand, int]):
    """Run every queued import, one at a time, in turns between people.

    Runs of the job never overlap, so an import still `running` when this starts
    was interrupted, and fails. Each import runs as its owner, capped by the token
    that queued it, and in its own transactions, so one failing leaves the others
    to run. Returns how many imports ran.
    """

    access: ClassVar[Access] = System()

    def __init__(
        self,
        uow: Callable[[], TransferUnitOfWork],
        guard: AccessGuard,
        store: ImportFileStore,
        actors: ImportActors,
        importer: ImporterFactory,
        reporter: Callable[[uuid.UUID], ProgressReporter],
    ) -> None:
        """Initialise with fresh units of work, the file store and the import."""
        self._uow = uow
        self._guard = guard
        self._store = store
        self._actors = actors
        self._importer = importer
        self._reporter = reporter

    async def _handle(self, request: RunQueuedImportsCommand, actor: Actor) -> int:
        """Fail the interrupted imports, then run the queue until it is empty."""
        await self._fail_interrupted()
        count = 0
        while (item := await self._take_next()) is not None:
            await self._run(item)
            count += 1
        return count

    async def _fail_interrupted(self) -> None:
        uow = self._uow()
        async with uow as repos:
            for item in await repos.imports.list_with_status(ImportStatus.RUNNING):
                item.fail(_INTERRUPTED, _now())
                await repos.imports.save(item)
                await self._delete_file(item)
            await uow.commit()

    async def _take_next(self) -> ItemImport | None:
        """Start the import whose turn it is, or return `None` when none waits."""
        uow = self._uow()
        async with uow as repos:
            waiting = await repos.imports.list_with_status(ImportStatus.QUEUED)
            if not waiting:
                return None
            served = await repos.imports.recent_owners(_SERVED_MEMORY)
            item = turn_order(waiting, served)[0]
            item.start(_now())
            await repos.imports.save(item)
            await uow.commit()
        return item

    async def _run(self, item: ItemImport) -> None:
        reporter = self._reporter(item.id)
        try:
            outcome = await self._import(item, reporter)
        except Exception as error:
            reason = failure_reason(error)
            logger.warning(
                "item import failed", import_id=item.id, error=type(error).__name__
            )
            await reporter.fail(reason)
            await self._finish(item, lambda found: found.fail(reason, _now()))
        else:
            await self._finish(item, lambda found: found.succeed(outcome, _now()))
        finally:
            await self._delete_file(item)

    async def _import(
        self, item: ItemImport, reporter: ProgressReporter
    ) -> ImportOutcome:
        owner = (
            None
            if item.owner_id is None
            else await self._actors.actor_for(item.owner_id, item.grants)
        )
        if owner is None:
            raise InvalidImportStateError(_OWNER_GONE)
        data = await self._store.read(owner.id, item.id)
        if data is None or item.options is None:
            raise InvalidImportStateError(_FILE_GONE)
        applied = await self._importer(owner, reporter).handle(
            import_request(item.options, data), owner
        )
        return ImportOutcome(
            items_added=applied.created.get(EntityKind.ITEM, 0),
            connections_added=applied.created.get(EntityKind.CONNECTION, 0),
        )

    async def _finish(
        self, item: ItemImport, end: Callable[[ItemImport], None]
    ) -> None:
        # Read again: the reporter has written progress since the import started.
        uow = self._uow()
        async with uow as repos:
            found = await repos.imports.get(item.id, scope=ContentFilter.everyone())
            if found is None:
                return
            end(found)
            await repos.imports.save(found)
            await uow.commit()

    async def _delete_file(self, item: ItemImport) -> None:
        await _delete_file(self._store, item)


@dataclass(frozen=True, kw_only=True)
class PruneItemImportsCommand:
    """Remove the imports that expired before `before`."""

    before: datetime


class PruneItemImports(
    CommandHandler[TransferUnitOfWork, PruneItemImportsCommand, int]
):
    """Remove expired uploads and their files, leaving queued and running ones.

    Returns how many were removed.
    """

    access: ClassVar[Access] = System()

    def __init__(
        self, uow: TransferUnitOfWork, guard: AccessGuard, store: ImportFileStore
    ) -> None:
        """Initialise with the unit of work and the file store."""
        super().__init__(uow, guard)
        self._store = store

    async def _handle(self, request: PruneItemImportsCommand, actor: Actor) -> int:
        """Delete each expired import's record, then its file."""
        async with self._uow as repos:
            expired = [
                item
                for item in await repos.imports.list_expired(request.before)
                if item.status not in (ImportStatus.QUEUED, ImportStatus.RUNNING)
            ]
            for item in expired:
                await repos.imports.delete(item.id)
            await self._uow.commit()
        for item in expired:
            await _delete_file(self._store, item)
        return len(expired)


async def _delete_file(store: ImportFileStore, item: ItemImport) -> None:
    # Only a row from before accounts has no owner, and so no file of its own.
    if item.owner_id is not None:
        await store.delete(item.owner_id, item.id)


def _now() -> datetime:
    return datetime.now(UTC)
