from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.domain.installation import (
    REMOVAL_ORDER,
    EntityKind,
    EntityRecord,
    Installation,
    Outcome,
)
from app.modules.examples.domain.removal import KEEP_IN_USE, Action, decide_removal
from app.modules.examples.ports.pack_targets import (
    CollectionTarget,
    CoverTarget,
    GraphTarget,
    Inspection,
    PresetTarget,
    RemoveResult,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@dataclass(kw_only=True, frozen=True, eq=False)
class KeptEntity:
    """An entity left in place on removal, and why."""

    kind: EntityKind
    ref: str
    label: str
    reason: str


async def settle_installation(
    installation: Installation,
    *,
    presets: PresetTarget,
    graph: GraphTarget,
    collections: CollectionTarget,
    covers: CoverTarget,
    persist: Callable[[Installation], Awaitable[None]],
) -> list[KeptEntity]:
    """Remove or keep every owned entity, saving after each one.

    Entities are handled in `REMOVAL_ORDER`, so by the time something is inspected
    everything that depended on it has already gone or been kept. Safe to call again
    on a half-finished installation: it only touches entities still owned.

    A kept cover is settled and recorded but not reported: the person sees the item
    that holds it, and covers are not something the pack lists or counts.
    """
    kept: list[KeptEntity] = []
    for kind in REMOVAL_ORDER:
        for record in reversed(installation.owned(kind)):
            reason = await _settle_one(
                installation,
                record,
                presets=presets,
                graph=graph,
                collections=collections,
                covers=covers,
            )
            await persist(installation)
            if reason is not None and record.kind is not EntityKind.COVER:
                kept.append(
                    KeptEntity(
                        kind=record.kind,
                        ref=record.ref,
                        label=record.label,
                        reason=reason,
                    )
                )
    return kept


async def inspect_record(
    record: EntityRecord,
    *,
    presets: PresetTarget,
    graph: GraphTarget,
    collections: CollectionTarget,
    covers: CoverTarget,
) -> Inspection | None:
    """Return the entity behind `record` as it is now, or `None` if it is gone."""
    if record.kind is EntityKind.PRESET:
        return await presets.inspect(record.entity_id)
    if record.kind is EntityKind.COLLECTION:
        return await collections.inspect(record.entity_id)
    if record.kind is EntityKind.COVER:
        return await covers.inspect(record.entity_id)
    return await graph.inspect(record.kind, record.entity_id)


async def _remove(
    record: EntityRecord,
    *,
    presets: PresetTarget,
    graph: GraphTarget,
    collections: CollectionTarget,
    covers: CoverTarget,
) -> RemoveResult:
    if record.kind is EntityKind.PRESET:
        return await presets.remove(record.entity_id)
    if record.kind is EntityKind.COLLECTION:
        return await collections.remove(record.entity_id)
    if record.kind is EntityKind.COVER:
        return await covers.remove(record.entity_id)
    return await graph.remove(record.kind, record.entity_id)


async def _settle_one(
    installation: Installation,
    record: EntityRecord,
    *,
    presets: PresetTarget,
    graph: GraphTarget,
    collections: CollectionTarget,
    covers: CoverTarget,
) -> str | None:
    """Settle one record; return the reason it was kept, or `None`."""
    inspection = await inspect_record(
        record, presets=presets, graph=graph, collections=collections, covers=covers
    )
    decision = decide_removal(
        record,
        None if inspection is None else content_hash(inspection.content),
        has_user_data=inspection is not None and inspection.has_user_data,
        still_in_use=inspection is not None and inspection.still_in_use,
    )
    if decision.action is Action.ALREADY_GONE:
        installation.settle(record.entity_id, Outcome.REMOVED)
        return None
    if decision.action is Action.KEEP:
        installation.settle(record.entity_id, Outcome.KEPT, decision.reason)
        return decision.reason

    result = await _remove(
        record, presets=presets, graph=graph, collections=collections, covers=covers
    )
    if result is RemoveResult.REFUSED_IN_USE:
        installation.settle(record.entity_id, Outcome.KEPT, KEEP_IN_USE)
        return KEEP_IN_USE
    installation.settle(record.entity_id, Outcome.REMOVED)
    return None
