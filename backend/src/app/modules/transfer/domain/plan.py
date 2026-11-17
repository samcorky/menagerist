from dataclasses import dataclass
from enum import StrEnum

from app.modules.transfer.domain.entity_kind import EntityKind


class PlanAction(StrEnum):
    """What applying a plan would do with one entity of the bundle.

    `AMBIGUOUS` is a row whose source key cannot be pinned to one entity: it is
    skipped, with the reason, and does not stop the rest being applied. Updating an
    entity and noticing one that is no longer in the source come with importing a
    source again (#234).
    """

    CREATE = "create"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"
    AMBIGUOUS = "ambiguous"


class ClashPolicy(StrEnum):
    """What planning does with a type whose name the person already uses.

    `SKIP` keeps theirs and plans the type `unchanged`; `CONFLICT` plans it as a
    conflict, which stops the bundle being applied.
    """

    SKIP = "skip"
    CONFLICT = "conflict"


@dataclass(kw_only=True, frozen=True, eq=False)
class PlannedEntity:
    """One entity of the bundle and what applying the plan would do with it."""

    kind: EntityKind
    ref: str
    label: str
    action: PlanAction
    reason: str | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class PlanBlocker:
    """Something that stops the whole bundle being applied.

    `code` names the error applying would raise, as the API's problem `title` does.
    """

    code: str
    reason: str


@dataclass(kw_only=True, frozen=True, eq=False)
class Plan:
    """What applying a bundle would do, worked out before anything is written."""

    bundle_id: str
    entities: tuple[PlannedEntity, ...]
    blockers: tuple[PlanBlocker, ...] = ()

    @property
    def ready(self) -> bool:
        """Whether the plan can be applied: nothing blocks it and nothing conflicts."""
        return not self.blockers and not self.conflicts

    @property
    def conflicts(self) -> tuple[PlannedEntity, ...]:
        """The entities that stop the plan being applied."""
        return self.with_action(PlanAction.CONFLICT)

    def with_action(self, action: PlanAction) -> tuple[PlannedEntity, ...]:
        """The entities applying would treat as `action`, in bundle order."""
        return tuple(e for e in self.entities if e.action is action)
