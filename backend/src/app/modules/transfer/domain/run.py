import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import InvalidRunStateError
from app.shared_kernel.mixins import Identifiable, Owned, Timestamped

if TYPE_CHECKING:
    from collections.abc import Sequence


class RunStatus(StrEnum):
    """Where a run is in its life. The values are stored, so they keep their names."""

    INSTALLING = "installing"
    INSTALLED = "installed"
    REMOVED = "removed"
    FAILED = "failed"


class Outcome(StrEnum):
    """Who owns an entity now."""

    OWNED = "owned"
    REMOVED = "removed"
    KEPT = "kept"


# The reverse of install order: a thing goes before whatever it depends on.
REMOVAL_ORDER = (
    EntityKind.COVER,
    EntityKind.CONNECTION,
    EntityKind.COLLECTION,
    EntityKind.ITEM,
    EntityKind.ITEM_TYPE,
    EntityKind.RELATIONSHIP_TYPE,
    EntityKind.PRESET,
)


@dataclass(kw_only=True, frozen=True, eq=False)
class EntityRecord:
    """One entity a run created."""

    kind: EntityKind
    ref: str
    label: str
    entity_id: uuid.UUID
    content_hash: str
    outcome: Outcome = Outcome.OWNED
    reason: str | None = None


@dataclass(kw_only=True, eq=False)
class Run(Identifiable, Owned, Timestamped):
    """The record of one bundle being installed, and what became of its entities.

    The ledger a bundle's removal works from: each entity it created, with the hash
    of its content as created, and whether the bundle still owns it.
    """

    bundle_id: str
    status: RunStatus
    entities: list[EntityRecord] = field(default_factory=list)
    installed_at: datetime | None = None
    removed_at: datetime | None = None

    @classmethod
    def start(cls, bundle_id: str, owner_id: uuid.UUID) -> Run:
        """Begin `owner_id`'s run of `bundle_id`, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            owner_id=owner_id,
            bundle_id=bundle_id,
            status=RunStatus.INSTALLING,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_active(self) -> bool:
        """Whether this run blocks a new install of the same bundle."""
        return self.status in (
            RunStatus.INSTALLING,
            RunStatus.INSTALLED,
        )

    def owned(self, kind: EntityKind | None = None) -> list[EntityRecord]:
        """Return the entities still owned by the bundle, optionally of one kind."""
        return [
            r
            for r in self.entities
            if r.outcome is Outcome.OWNED and (kind is None or r.kind is kind)
        ]

    def record(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        entity_id: uuid.UUID,
        content_hash: str,
    ) -> None:
        """Record an entity the bundle just created."""
        self._require(RunStatus.INSTALLING)
        self._append(kind, ref, label, entity_id, content_hash)

    def record_late(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        entity_id: uuid.UUID,
        content_hash: str,
    ) -> None:
        """Record an entity created after the install finished (a link).

        A settled record of the same `ref` (the link was removed or kept earlier) is
        replaced, so one logical link never counts twice.
        """
        self._require(RunStatus.INSTALLING, RunStatus.INSTALLED)
        self.entities = [
            r
            for r in self.entities
            if not (r.kind is kind and r.ref == ref and r.outcome is not Outcome.OWNED)
        ]
        self._append(kind, ref, label, entity_id, content_hash)

    def _append(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        entity_id: uuid.UUID,
        content_hash: str,
    ) -> None:
        self.entities.append(
            EntityRecord(
                kind=kind,
                ref=ref,
                label=label,
                entity_id=entity_id,
                content_hash=content_hash,
            )
        )
        self.touch()

    def settle(
        self, entity_id: uuid.UUID, outcome: Outcome, reason: str | None = None
    ) -> None:
        """Mark an owned entity as removed, or kept (and so no longer the bundle's)."""
        if outcome is Outcome.OWNED:
            raise InvalidRunStateError(
                "an entity can only be settled as removed or kept"
            )
        for index, record in enumerate(self.entities):
            if record.entity_id == entity_id and record.outcome is Outcome.OWNED:
                self.entities[index] = replace(record, outcome=outcome, reason=reason)
                self.touch()
                return
        raise InvalidRunStateError(f"no owned entity {entity_id} to settle")

    def mark_installed(self) -> None:
        """The install finished."""
        self._require(RunStatus.INSTALLING)
        self.status = RunStatus.INSTALLED
        self.installed_at = datetime.now(UTC)
        self.touch()

    def mark_failed(self) -> None:
        """The install failed and everything it created has been dealt with."""
        self._require(RunStatus.INSTALLING)
        self._require_nothing_owned()
        self.status = RunStatus.FAILED
        self.touch()

    def mark_removed(self) -> None:
        """The bundle was removed and everything it created has been dealt with."""
        self._require(RunStatus.INSTALLING, RunStatus.INSTALLED)
        self._require_nothing_owned()
        self.status = RunStatus.REMOVED
        self.removed_at = datetime.now(UTC)
        self.touch()

    def _require(self, *allowed: RunStatus) -> None:
        if self.status not in allowed:
            raise InvalidRunStateError(
                f"run is {self.status}, which does not allow this"
            )

    def _require_nothing_owned(self) -> None:
        if self.owned():
            raise InvalidRunStateError("the bundle still owns entities")


def adoptable_records(
    runs: Sequence[Run],
) -> dict[tuple[EntityKind, str], EntityRecord]:
    """Return the entities a bundle left behind and may take back, by (kind, ref).

    `runs` must be newest first. For each (kind, ref) the newest record
    decides: it is adoptable only if it was kept, so a later removal or a later
    owned record supersedes older kept ones.
    """
    newest: dict[tuple[EntityKind, str], EntityRecord] = {}
    for run in runs:
        for record in run.entities:
            newest.setdefault((record.kind, record.ref), record)
    return {key: r for key, r in newest.items() if r.outcome is Outcome.KEPT}
