from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.transfer.application.content_hash import content_hash
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.removal import KEEP_IN_USE, Action, decide_removal
from app.modules.transfer.domain.run import REMOVAL_ORDER, EntityRecord, Outcome, Run
from app.modules.transfer.ports.targets import (
    CollectionTarget,
    EntityTarget,
    GraphTarget,
    Inspection,
    PresetTarget,
    RemoveResult,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence


@dataclass(kw_only=True, frozen=True, eq=False)
class KeptEntity:
    """An entity left in place on removal, and why."""

    kind: EntityKind
    ref: str
    label: str
    reason: str


@dataclass(kw_only=True, frozen=True, eq=False)
class RemovalTargets:
    """Where each kind of entity a run created is inspected and removed.

    `others` holds the kinds the shared targets do not cover, such as an
    example's generated covers.
    """

    presets: PresetTarget
    graph: GraphTarget
    collections: CollectionTarget
    others: Mapping[EntityKind, EntityTarget]


async def settle_run(
    run: Run,
    targets: RemovalTargets,
    *,
    persist: Callable[[Run], Awaitable[None]],
) -> list[KeptEntity]:
    """Remove or keep every owned entity, saving after each kind.

    Entities are handled in `REMOVAL_ORDER`, so by the time something is inspected
    everything that depended on it has already gone or been kept. Safe to call again
    on a half-finished run: it only touches entities still owned, and an entity
    removed but not yet saved reads as already gone.
    """
    kept: list[KeptEntity] = []
    for kind in REMOVAL_ORDER:
        for record in reversed(run.owned(kind)):
            reason = await _settle_one(run, record, targets)
            if reason is not None:
                kept.append(_kept(record, reason))
        await persist(run)
    return kept


async def settle_records(
    run: Run,
    records: Sequence[EntityRecord],
    targets: RemovalTargets,
    *,
    persist: Callable[[Run], Awaitable[None]],
) -> list[KeptEntity]:
    """Remove or keep just `records` of `run`, then save it once."""
    kept: list[KeptEntity] = []
    for record in records:
        reason = await _settle_one(run, record, targets)
        if reason is not None:
            kept.append(_kept(record, reason))
    await persist(run)
    return kept


async def inspect_record(
    record: EntityRecord, targets: RemovalTargets
) -> Inspection | None:
    """Return the entity behind `record` as it is now, or `None` if it is gone."""
    single = _single_kind_target(record.kind, targets)
    if single is not None:
        return await single.inspect(record.entity_id)
    return await targets.graph.inspect(record.kind, record.entity_id)


def _kept(record: EntityRecord, reason: str) -> KeptEntity:
    return KeptEntity(
        kind=record.kind, ref=record.ref, label=record.label, reason=reason
    )


def _single_kind_target(
    kind: EntityKind, targets: RemovalTargets
) -> EntityTarget | None:
    """The target for a kind kept outside the graph, or `None` for graph kinds."""
    if kind is EntityKind.PRESET:
        return targets.presets
    if kind is EntityKind.COLLECTION:
        return targets.collections
    return targets.others.get(kind)


async def _remove(record: EntityRecord, targets: RemovalTargets) -> RemoveResult:
    single = _single_kind_target(record.kind, targets)
    if single is not None:
        return await single.remove(record.entity_id)
    return await targets.graph.remove(record.kind, record.entity_id)


async def _settle_one(
    run: Run, record: EntityRecord, targets: RemovalTargets
) -> str | None:
    """Settle one record; return the reason it was kept, or `None`."""
    inspection = await inspect_record(record, targets)
    decision = decide_removal(
        record,
        None if inspection is None else content_hash(inspection.content),
        has_user_data=inspection is not None and inspection.has_user_data,
        still_in_use=inspection is not None and inspection.still_in_use,
    )
    if decision.action is Action.ALREADY_GONE:
        run.settle(record.entity_id, Outcome.REMOVED)
        return None
    if decision.action is Action.KEEP:
        run.settle(record.entity_id, Outcome.KEPT, decision.reason)
        return decision.reason

    result = await _remove(record, targets)
    if result is RemoveResult.REFUSED_IN_USE:
        run.settle(record.entity_id, Outcome.KEPT, KEEP_IN_USE)
        return KEEP_IN_USE
    run.settle(record.entity_id, Outcome.REMOVED)
    return None
