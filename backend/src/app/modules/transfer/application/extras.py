"""What only some sources bring to planning and applying a bundle.

A file or a catalogue entry is planned and applied from its bundle alone. An example
pack also takes back what an earlier removal kept, builds on the packs it requires,
draws covers and records each entity it makes in a run, so it can be undone. Those
travel in `BundleExtras`, whose defaults add nothing, so the other sources never see
them.
"""

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from app.modules.transfer.application.content_hash import content_hash
from app.modules.transfer.application.removal import inspect_record
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import PlanBlocker
from app.modules.transfer.domain.run import EntityRecord, Run, adoptable_records
from app.modules.transfer.ports.targets import (
    CollectionTarget,
    CoverTarget,
    Created,
    PresetOutcome,
)
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.modules.transfer.application.removal import RemovalTargets
    from app.modules.transfer.domain.bundle import Bundle, BundlePreset
    from app.modules.transfer.ports.run_repository import RunRepository
    from app.shared_kernel.content_filter import ContentFilter

Key = tuple[EntityKind, str]


@dataclass(kw_only=True, frozen=True, eq=False)
class Adoption:
    """An entity an earlier run kept that is still live, and as it is now."""

    record: EntityRecord
    content: dict[str, Any]


@dataclass(kw_only=True, frozen=True, eq=False)
class ResolvedRef:
    """A live entity of a required pack: its id, and its slug or name."""

    entity_id: uuid.UUID
    slug: str | None = None
    name: str | None = None


ResolvedRefs = dict[tuple[EntityKind, str, str], ResolvedRef]


class Ledger(Protocol):
    """Records what applying a bundle makes, so the run can be undone."""

    async def presets(
        self, outcomes: Sequence[PresetOutcome], specs: Sequence[BundlePreset]
    ) -> None:
        """Record the presets the batch created; an existing one is not ours."""
        ...

    async def created(
        self, kind: EntityKind, ref: str, label: str, created: Created
    ) -> None:
        """Record one entity as it is made."""
        ...

    async def adopted(self, adoption: Adoption, ref: str, label: str) -> None:
        """Record a kept entity as the run's own, with its original hash."""
        ...


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleExtras:
    """The source-specific inputs to `plan_bundle` and `apply_bundle`.

    `adoptions` are what an earlier run kept, taken back instead of created again.
    `external` are the live entities of the packs the bundle requires, which its
    `pack:ref` references name. `blockers` stop the plan whatever else it holds.
    `covers` draws a cover for each item whose type has a style in `cover_styles`
    (by item type ref, required packs' types included). `ledger` records each entity
    as it is made.
    """

    adoptions: Mapping[Key, Adoption] = field(default_factory=dict)
    external: ResolvedRefs = field(default_factory=dict)
    blockers: tuple[PlanBlocker, ...] = ()
    cover_styles: Mapping[str, str] = field(default_factory=dict)
    covers: CoverTarget | None = None
    collections: CollectionTarget | None = None
    ledger: Ledger | None = None


class RunLedger:
    """A `Ledger` that records into a `Run`, saving after each entity.

    `adopted_keys` lists what was taken back rather than made, so a caller can tell
    the two apart.
    """

    def __init__(self, run: Run, persist: Callable[[Run], Awaitable[None]]) -> None:
        """Initialise with the run to record into and how to save it."""
        self._run = run
        self._persist = persist
        self.adopted_keys: set[Key] = set()

    async def presets(
        self, outcomes: Sequence[PresetOutcome], specs: Sequence[BundlePreset]
    ) -> None:
        """Record the presets the batch created, saving once for the batch."""
        for outcome, spec in zip(outcomes, specs, strict=True):
            if outcome.created:  # an identical preset that already existed is not ours
                self._run.record(
                    EntityKind.PRESET,
                    outcome.ref,
                    spec.label,
                    outcome.entity_id,
                    content_hash(outcome.content),
                )
        await self._persist(self._run)

    async def created(
        self, kind: EntityKind, ref: str, label: str, created: Created
    ) -> None:
        """Record one entity as it is made."""
        self._run.record(
            kind, ref, label, created.entity_id, content_hash(created.content)
        )
        await self._persist(self._run)

    async def adopted(self, adoption: Adoption, ref: str, label: str) -> None:
        """Record a kept entity as the run's own, with its original hash."""
        record = adoption.record
        self._run.record(record.kind, ref, label, record.entity_id, record.content_hash)
        self.adopted_keys.add((record.kind, ref))
        await self._persist(self._run)


async def find_adoptions(
    bundle: Bundle,
    cover_styles: Mapping[str, str],
    runs: RunRepository,
    scope: ContentFilter,
    targets: RemovalTargets,
) -> dict[Key, Adoption]:
    """Return what the person's earlier runs of `bundle` kept that still fits.

    An entity is found only if it is still live and, for a type, still has the slug
    the bundle gives it.
    """
    kept = adoptable_records(await runs.list_for_bundle(bundle.id, scope=scope))
    slugs: dict[Key, str | None] = {
        (EntityKind.RELATIONSHIP_TYPE, r.ref): slugify(r.slug)
        for r in bundle.relationship_types
    }
    slugs |= {(EntityKind.ITEM_TYPE, t.ref): t.slug for t in bundle.item_types}
    slugs |= {(EntityKind.ITEM, i.ref): None for i in bundle.items}
    slugs |= {
        (EntityKind.CONNECTION, connection_ref(n)): None
        for n in range(len(bundle.connections))
    }
    slugs |= {(EntityKind.COLLECTION, c.ref): None for c in bundle.collections}
    slugs |= {
        (EntityKind.COVER, i.ref): None
        for i in bundle.items
        if i.type_ref in cover_styles
    }

    found: dict[Key, Adoption] = {}
    for key, expected_slug in slugs.items():
        record = kept.get(key)
        if record is None:
            continue
        inspection = await inspect_record(record, targets)
        if inspection is None:
            continue
        if expected_slug is not None and inspection.content["slug"] != expected_slug:
            continue
        found[key] = Adoption(record=record, content=inspection.content)
    return found


def connection_ref(index: int) -> str:
    """Return the record ref of the `index`th connection of a bundle."""
    return f"connection-{index}"
