"""A CSV file uploaded to import, and what became of it.

The file is stored once; inspecting and previewing read it by id, and running it
queues the import for the worker, which works through the queue one import at a
time, taking turns between people.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from app.modules.transfer.domain.errors import InvalidImportStateError
from app.modules.transfer.domain.tabular import (
    ColumnMapping,
    ConnectionColumn,
    DayMonthOrder,
)
from app.shared_kernel.mixins import Identifiable, Owned, Timestamped
from app.shared_kernel.progress import ProgressSnapshot

if TYPE_CHECKING:
    from collections.abc import Sequence


MAX_FILENAME_LENGTH = 255


class ImportStatus(StrEnum):
    """Where an uploaded file is in its life. The values are stored."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


_FINISHED = (ImportStatus.SUCCEEDED, ImportStatus.FAILED)


@dataclass(frozen=True, kw_only=True)
class ImportOptions:
    """How to import the file: everything a run needs besides the file itself."""

    item_type: str
    mapping: tuple[ColumnMapping, ...] = ()
    list_separator: str = ","
    day_month_order: DayMonthOrder = DayMonthOrder.DAY_FIRST
    key_field: str | None = None
    restore: tuple[str, ...] = ()
    connections: tuple[ConnectionColumn, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ImportOutcome:
    """What a finished import added."""

    items_added: int
    connections_added: int


@dataclass(kw_only=True, eq=False)
class ItemImport(Identifiable, Owned, Timestamped):
    """One uploaded file and its import.

    `grants` is the permission ceiling of the token that queued it (`None` for a
    session), so the worker runs it with no more than the person asked with.
    """

    filename: str
    size: int
    status: ImportStatus
    expires_at: datetime
    options: ImportOptions | None = None
    grants: frozenset[str] | None = None
    progress: ProgressSnapshot | None = None
    outcome: ImportOutcome | None = None
    failure: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def upload(
        cls,
        *,
        owner_id: uuid.UUID,
        filename: str,
        size: int,
        now: datetime,
        keep_for: timedelta,
    ) -> ItemImport:
        """Record a file `owner_id` just stored, kept until `keep_for` from `now`."""
        return cls(
            id=uuid.uuid7(),
            owner_id=owner_id,
            filename=filename.strip()[:MAX_FILENAME_LENGTH] or "import.csv",
            size=size,
            status=ImportStatus.UPLOADED,
            expires_at=now + keep_for,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_finished(self) -> bool:
        """Whether the import has run, whichever way it ended."""
        return self.status in _FINISHED

    def queue(
        self, options: ImportOptions, grants: frozenset[str] | None, now: datetime
    ) -> None:
        """Ask for the file to be imported with `options`.

        Raises:
            InvalidImportStateError: it is already queued, running or finished.
        """
        self._require(ImportStatus.UPLOADED)
        self.options = options
        self.grants = grants
        self.status = ImportStatus.QUEUED
        self.queued_at = now
        self.updated_at = now

    def start(self, now: datetime) -> None:
        """The worker took the import."""
        self._require(ImportStatus.QUEUED)
        self.status = ImportStatus.RUNNING
        self.started_at = now
        self.updated_at = now

    def report(self, snapshot: ProgressSnapshot, now: datetime) -> None:
        """Keep how far the running import has got."""
        if self.status is not ImportStatus.RUNNING:
            return  # a late write after the import ended changes nothing
        self.progress = snapshot
        self.updated_at = now

    def succeed(self, outcome: ImportOutcome, now: datetime) -> None:
        """The import finished and added what `outcome` says."""
        self._require(ImportStatus.RUNNING)
        self.status = ImportStatus.SUCCEEDED
        self.outcome = outcome
        self.finished_at = now
        self.updated_at = now

    def fail(self, reason: str, now: datetime) -> None:
        """The import could not finish, or could not start; `reason` says why."""
        self._require(ImportStatus.QUEUED, ImportStatus.RUNNING)
        self.status = ImportStatus.FAILED
        self.failure = reason
        self.finished_at = now
        self.updated_at = now

    def _require(self, *allowed: ImportStatus) -> None:
        if self.status not in allowed:
            raise InvalidImportStateError(
                f"This import is {self.status}, so it cannot do that."
            )


def turn_order(
    waiting: Sequence[ItemImport], served: Sequence[uuid.UUID]
) -> list[ItemImport]:
    """Put the waiting imports in the order the worker will run them.

    The worker runs `[0]` next, and each waiting import's place in the list is how
    many run before it, so both must agree. People take turns: one person's five
    files must not hold back everyone else's one. Each person's own imports keep
    the order they were queued in.

    Args:
        waiting: Every queued import, oldest first.
        served: The owners of the imports started most recently, newest first.

    Returns:
        The same imports, the next to run first.
    """
    queues: dict[uuid.UUID | None, list[ItemImport]] = {}
    for item in waiting:
        queues.setdefault(item.owner_id, []).append(item)
    since: dict[uuid.UUID | None, int] = {}
    for turns_ago, owner in enumerate(served):
        since.setdefault(owner, turns_ago)
    # Longest since their last turn goes first; nobody recent beats everyone, and
    # ties keep the order of each person's oldest waiting import (a stable sort).
    owners = sorted(queues, key=lambda owner: -since.get(owner, len(served)))
    rounds = max((len(q) for q in queues.values()), default=0)
    return [
        queues[owner][turn]
        for turn in range(rounds)
        for owner in owners
        if turn < len(queues[owner])
    ]
