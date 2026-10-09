import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.shared_kernel.mixins import Identifiable, Timestamped

if TYPE_CHECKING:
    from collections.abc import Sequence


class InstallationStatus(StrEnum):
    """Where an installation is in its life."""

    INSTALLING = "installing"
    INSTALLED = "installed"
    REMOVED = "removed"
    FAILED = "failed"


class EntityKind(StrEnum):
    """What kind of entity an installation created."""

    PRESET = "preset"
    RELATIONSHIP_TYPE = "relationship_type"
    ITEM_TYPE = "item_type"
    ITEM = "item"
    CONNECTION = "connection"
    COLLECTION = "collection"


class Outcome(StrEnum):
    """Who owns an entity now."""

    OWNED = "owned"
    REMOVED = "removed"
    KEPT = "kept"


# The reverse of install order: a thing goes before whatever it depends on.
REMOVAL_ORDER = (
    EntityKind.CONNECTION,
    EntityKind.COLLECTION,
    EntityKind.ITEM,
    EntityKind.ITEM_TYPE,
    EntityKind.RELATIONSHIP_TYPE,
    EntityKind.PRESET,
)


@dataclass(kw_only=True, frozen=True, eq=False)
class EntityRecord:
    """One entity an installation created."""

    kind: EntityKind
    ref: str
    label: str
    entity_id: uuid.UUID
    content_hash: str
    outcome: Outcome = Outcome.OWNED
    reason: str | None = None


@dataclass(kw_only=True, eq=False)
class Installation(Identifiable, Timestamped):
    """The record of one pack being installed, and what became of its entities."""

    pack_id: str
    status: InstallationStatus
    entities: list[EntityRecord] = field(default_factory=list)
    installed_at: datetime | None = None
    removed_at: datetime | None = None

    @classmethod
    def start(cls, pack_id: str) -> Installation:
        """Begin an installation, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            pack_id=pack_id,
            status=InstallationStatus.INSTALLING,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_active(self) -> bool:
        """Whether this installation blocks a new install of the same pack."""
        return self.status in (
            InstallationStatus.INSTALLING,
            InstallationStatus.INSTALLED,
        )

    def owned(self, kind: EntityKind | None = None) -> list[EntityRecord]:
        """Return the entities still owned by the pack, optionally of one kind."""
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
        """Record an entity the pack just created."""
        self._require(InstallationStatus.INSTALLING)
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
        """Mark an owned entity as removed, or kept (and so no longer the pack's)."""
        if outcome is Outcome.OWNED:
            raise InvalidInstallationStateError(
                "an entity can only be settled as removed or kept"
            )
        for index, record in enumerate(self.entities):
            if record.entity_id == entity_id and record.outcome is Outcome.OWNED:
                self.entities[index] = replace(record, outcome=outcome, reason=reason)
                self.touch()
                return
        raise InvalidInstallationStateError(f"no owned entity {entity_id} to settle")

    def mark_installed(self) -> None:
        """The install finished."""
        self._require(InstallationStatus.INSTALLING)
        self.status = InstallationStatus.INSTALLED
        self.installed_at = datetime.now(UTC)
        self.touch()

    def mark_failed(self) -> None:
        """The install failed and everything it created has been dealt with."""
        self._require(InstallationStatus.INSTALLING)
        self._require_nothing_owned()
        self.status = InstallationStatus.FAILED
        self.touch()

    def mark_removed(self) -> None:
        """The pack was removed and everything it created has been dealt with."""
        self._require(InstallationStatus.INSTALLING, InstallationStatus.INSTALLED)
        self._require_nothing_owned()
        self.status = InstallationStatus.REMOVED
        self.removed_at = datetime.now(UTC)
        self.touch()

    def _require(self, *allowed: InstallationStatus) -> None:
        if self.status not in allowed:
            raise InvalidInstallationStateError(
                f"installation is {self.status}, which does not allow this"
            )

    def _require_nothing_owned(self) -> None:
        if self.owned():
            raise InvalidInstallationStateError("the pack still owns entities")


def adoptable_records(
    installations: Sequence[Installation],
) -> dict[tuple[EntityKind, str], EntityRecord]:
    """Return the entities a pack left behind and may take back, by (kind, ref).

    `installations` must be newest first. For each (kind, ref) the newest record
    decides: it is adoptable only if it was kept, so a later removal or a later
    owned record supersedes older kept ones.
    """
    newest: dict[tuple[EntityKind, str], EntityRecord] = {}
    for installation in installations:
        for record in installation.entities:
            newest.setdefault((record.kind, record.ref), record)
    return {key: r for key, r in newest.items() if r.outcome is Outcome.KEPT}
