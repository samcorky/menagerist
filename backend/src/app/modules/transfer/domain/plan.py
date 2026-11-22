import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.modules.transfer.domain.entity_kind import EntityKind


class PlanAction(StrEnum):
    """What applying a plan would do with one entity of the bundle.

    `UNCHANGED` is one the person already has. `SKIP` is left out, with the reason:
    it has no key, something it joins is not imported, or the person deleted it
    after importing it. `AMBIGUOUS` names more than one entity, so it is left out
    too. Neither stops the rest being applied. Updating an entity and noticing one
    that is no longer in the source come with importing a source again (#234).
    """

    CREATE = "create"
    UNCHANGED = "unchanged"
    SKIP = "skip"
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
    """One entity of the bundle and what applying the plan would do with it.

    An item recognised as one the person has names it in `matched_id` and
    `matched_name`, and `changed` lists the fields whose value in the source differs
    from what was last imported (`name`, `description`, `tags`, `attributes.<key>`).
    `source_key` is the key the entity has in its source, if it has one, and
    `deleted` marks one left out because the person deleted it after importing it,
    which sending its key in `restore` brings back.
    """

    kind: EntityKind
    ref: str
    label: str
    action: PlanAction
    reason: str | None = None
    matched_id: uuid.UUID | None = None
    matched_name: str | None = None
    changed: tuple[str, ...] = ()
    source_key: str | None = None
    deleted: bool = False


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
