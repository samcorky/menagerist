"""Plan a bundle against what the person has, then apply that plan through targets.

Every source goes through here: a decoded file, a catalogue entry. Planning reads
only, so the same plan is a dry run and, applied, what the import does.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.modules.transfer.application.content_hash import preset_key
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import BundleConflictError
from app.modules.transfer.domain.plan import (
    ClashPolicy,
    Plan,
    PlanAction,
    PlannedEntity,
)

if TYPE_CHECKING:
    import uuid

    from app.modules.transfer.domain.bundle import Bundle
    from app.modules.transfer.ports.targets import GraphTarget, PresetTarget

_PRESET_EXISTS = "You already have one the same."
_NAME_TAKEN = "You already have one with this name."
_NOUNS = {
    EntityKind.ITEM_TYPE: "an item type",
    EntityKind.RELATIONSHIP_TYPE: "a relationship type",
}


@dataclass(kw_only=True, frozen=True, eq=False)
class AppliedBundle:
    """What applying a plan created, and what it left as the person had it."""

    bundle_id: str
    created: dict[EntityKind, int] = field(default_factory=dict)
    skipped: dict[EntityKind, int] = field(default_factory=dict)

    @property
    def total_created(self) -> int:
        """Everything created, of every kind."""
        return sum(self.created.values())

    @property
    def total_skipped(self) -> int:
        """Everything left as it was, of every kind."""
        return sum(self.skipped.values())


async def plan_bundle(
    bundle: Bundle,
    presets: PresetTarget,
    graph: GraphTarget,
    *,
    clash: ClashPolicy,
) -> Plan:
    """Work out what applying `bundle` would do, without writing anything.

    A preset is `unchanged` when the person has an identical one or it repeats one
    earlier in the bundle. A type whose name is taken is `unchanged` or a conflict,
    as `clash` says. The presets are checked first, so a bundle that applying would
    refuse is refused here too.

    Raises:
        ValidationError: a preset is malformed, or there are too many.
    """
    await presets.check(bundle.presets)
    entities: list[PlannedEntity] = []
    have = await presets.existing(bundle.presets)
    first: dict[str, str] = {}
    for spec, existing in zip(bundle.presets, have, strict=True):
        key = preset_key(spec.kind, spec.label, spec.definition)
        reason: str | None = None
        if existing:
            reason = _PRESET_EXISTS
        elif key in first:
            reason = f"The same as '{first[key]}', earlier in this file."
        else:
            first[key] = spec.ref
        entities.append(_planned(EntityKind.PRESET, spec.ref, spec.label, reason))
    for kind, specs in (
        (EntityKind.RELATIONSHIP_TYPE, bundle.relationship_types),
        (EntityKind.ITEM_TYPE, bundle.item_types),
    ):
        for type_spec in specs:
            taken = await graph.slug_taken(kind, type_spec.slug)
            entities.append(
                _type_entity(
                    kind,
                    type_spec.ref,
                    type_spec.label,
                    type_spec.slug,
                    taken=taken,
                    clash=clash,
                )
            )
    return Plan(bundle_id=bundle.id, entities=tuple(entities))


def _planned(
    kind: EntityKind, ref: str, label: str, reason: str | None
) -> PlannedEntity:
    action = PlanAction.CREATE if reason is None else PlanAction.UNCHANGED
    return PlannedEntity(kind=kind, ref=ref, label=label, action=action, reason=reason)


def _type_entity(
    kind: EntityKind,
    ref: str,
    label: str,
    slug: str,
    *,
    taken: bool,
    clash: ClashPolicy,
) -> PlannedEntity:
    if not taken:
        return _planned(kind, ref, label, None)
    if clash is ClashPolicy.SKIP:
        return _planned(kind, ref, label, _NAME_TAKEN)
    return PlannedEntity(
        kind=kind,
        ref=ref,
        label=label,
        action=PlanAction.CONFLICT,
        reason=(
            f"You already have {_NOUNS[kind]} called '{slug}'. "
            + "Rename or remove it, then try again."
        ),
    )


async def apply_bundle(
    plan: Plan, bundle: Bundle, presets: PresetTarget, graph: GraphTarget
) -> AppliedBundle:
    """Create what `plan` marks `create`, through the targets, in plan order.

    The presets are ensured as one batch, so a type's `$preset` markers resolve to
    the person's existing copy as well as a new one; the target creates only those
    the plan marks `create`, as it uses the same notion of "the same".

    Raises:
        BundleConflictError: the plan has a conflict or a blocker.
    """
    if not plan.ready:
        problem = (
            plan.conflicts[0].reason if plan.conflicts else plan.blockers[0].reason
        )
        raise BundleConflictError(problem or "The bundle cannot be applied.")
    outcomes = await presets.ensure(bundle.presets)
    preset_ids: dict[str, uuid.UUID] = {o.ref: o.entity_id for o in outcomes}
    created = {EntityKind.PRESET: sum(1 for o in outcomes if o.created)}
    creating = {(e.kind, e.ref) for e in plan.with_action(PlanAction.CREATE)}
    rel_types = [
        r
        for r in bundle.relationship_types
        if (EntityKind.RELATIONSHIP_TYPE, r.ref) in creating
    ]
    for rel in rel_types:
        await graph.create_relationship_type(rel, preset_ids)
    item_types = [
        t for t in bundle.item_types if (EntityKind.ITEM_TYPE, t.ref) in creating
    ]
    for item_type in item_types:
        await graph.create_item_type(item_type, preset_ids)
    created[EntityKind.RELATIONSHIP_TYPE] = len(rel_types)
    created[EntityKind.ITEM_TYPE] = len(item_types)
    totals = {
        EntityKind.PRESET: len(bundle.presets),
        EntityKind.RELATIONSHIP_TYPE: len(bundle.relationship_types),
        EntityKind.ITEM_TYPE: len(bundle.item_types),
    }
    return AppliedBundle(
        bundle_id=bundle.id,
        created=created,
        skipped={kind: totals[kind] - created[kind] for kind in totals},
    )
