from typing import TYPE_CHECKING

from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import Plan, PlanAction, PlannedEntity

if TYPE_CHECKING:
    from app.modules.catalogue.domain.entry import CatalogueEntry
    from app.modules.transfer.ports.targets import GraphTarget, PresetTarget

_PRESET_EXISTS = "You already have one the same."
_NAME_TAKEN = "You already have one with this name."


def _entity(
    kind: EntityKind, ref: str, label: str, *, present: bool, reason: str
) -> PlannedEntity:
    if present:
        return PlannedEntity(
            kind=kind, ref=ref, label=label, action=PlanAction.UNCHANGED, reason=reason
        )
    return PlannedEntity(kind=kind, ref=ref, label=label, action=PlanAction.CREATE)


async def plan_entry(
    entry: CatalogueEntry, presets: PresetTarget, graph: GraphTarget
) -> Plan:
    """Work out what installing `entry` would create, without writing anything.

    What the person already has is `unchanged`: an identical preset, or a type whose
    name is taken. A catalogue install skips those rather than conflicting, so the
    plan is always ready.
    """
    present = await presets.existing(entry.presets)
    entities = [
        _entity(EntityKind.PRESET, p.ref, p.label, present=have, reason=_PRESET_EXISTS)
        for p, have in zip(entry.presets, present, strict=True)
    ]
    for spec in entry.item_types:
        taken = await graph.slug_taken(EntityKind.ITEM_TYPE, spec.slug)
        entities.append(
            _entity(
                EntityKind.ITEM_TYPE,
                spec.ref,
                spec.label,
                present=taken,
                reason=_NAME_TAKEN,
            )
        )
    for rel in entry.relationship_types:
        taken = await graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, rel.slug)
        entities.append(
            _entity(
                EntityKind.RELATIONSHIP_TYPE,
                rel.ref,
                rel.label,
                present=taken,
                reason=_NAME_TAKEN,
            )
        )
    return Plan(bundle_id=entry.id, entities=tuple(entities))
