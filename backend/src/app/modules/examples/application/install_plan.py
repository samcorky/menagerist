from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from app.modules.examples.application.external_refs import (
    ResolvedRefs,
    resolve_external_refs,
)
from app.modules.examples.domain.errors import (
    PackAlreadyInstalledError,
    RequirementsNotMetError,
    SlugClashError,
)
from app.modules.examples.domain.pack import ExamplePack
from app.modules.transfer.application.removal import inspect_record
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import (
    Plan,
    PlanAction,
    PlanBlocker,
    PlannedEntity,
)
from app.modules.transfer.domain.run import EntityRecord, adoptable_records
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    import uuid

    from app.modules.examples.ports.cover_target import CoverTarget
    from app.modules.examples.ports.pack_catalogue import PackCatalogue
    from app.modules.transfer.application.removal import RemovalTargets
    from app.modules.transfer.ports.run_repository import RunRepository
    from app.shared_kernel.content_filter import ContentFilter

Key = tuple[EntityKind, str]

_TAKEN_BACK = "Kept from an earlier install, and taken back as it is."
_PRESET_EXISTS = "You already have one the same."


@dataclass(kw_only=True, frozen=True, eq=False)
class Adoption:
    """An entity an earlier install kept that is still live, and as it is now."""

    record: EntityRecord
    content: dict[str, Any]


@dataclass(kw_only=True, frozen=True, eq=False)
class InstallPlan:
    """Everything an install needs, worked out before anything is written.

    `report` is what a dry run returns. `errors` are what applying the plan raises,
    in order, so an install refuses exactly what the report shows as blocking.
    """

    pack: ExamplePack
    report: Plan
    external: ResolvedRefs
    cover_styles: dict[str, str]
    adoptions: dict[Key, Adoption]
    errors: tuple[ConflictError, ...] = ()

    def action(self, kind: EntityKind, ref: str) -> PlanAction | None:
        """What the plan does with one entity, or `None` if it is not in the plan."""
        return next(
            (e.action for e in self.report.entities if (e.kind, e.ref) == (kind, ref)),
            None,
        )


async def plan_install(
    pack: ExamplePack,
    *,
    runs: RunRepository,
    scope: ContentFilter,
    catalogue: PackCatalogue,
    targets: RemovalTargets,
    covers: CoverTarget,
) -> InstallPlan:
    """Work out what installing `pack` would create, take back and refuse.

    Nothing is written. A pack that is installed already, or whose last install did
    not finish, has nothing else worth planning, so its report lists no entities.
    """
    cover_styles = await _cover_styles(pack, catalogue)
    if await runs.get_active_for_bundle(pack.id, scope=scope) is not None:
        error = PackAlreadyInstalledError(
            f"'{pack.id}' is already installed, or an earlier install did not "
            + "finish. Remove it first."
        )
        return InstallPlan(
            pack=pack,
            report=Plan(bundle_id=pack.id, entities=(), blockers=(_blocker(error),)),
            external={},
            cover_styles=cover_styles,
            adoptions={},
            errors=(error,),
        )

    blocking: list[ConflictError] = []
    external: ResolvedRefs = {}
    if pack.requires:
        try:
            external = await resolve_external_refs(
                pack, await runs.list_active(scope=scope), targets.graph, catalogue
            )
        except RequirementsNotMetError as exc:
            blocking.append(exc)
    kept = await _kept(pack, cover_styles, runs, scope, targets)
    planner = _Planner(pack=pack, external=external, kept=kept)
    planner.presets(await targets.presets.existing(pack.presets))
    clashes = await planner.types(targets)
    planner.items()
    planner.connections()
    planner.collections()
    await planner.covers(cover_styles, covers)

    return InstallPlan(
        pack=pack,
        report=Plan(
            bundle_id=pack.id,
            entities=tuple(planner.entities),
            blockers=tuple(_blocker(e) for e in blocking),
        ),
        external=external,
        cover_styles=cover_styles,
        adoptions=planner.adoptions,
        errors=(*blocking, *clashes),
    )


def _blocker(error: ConflictError) -> PlanBlocker:
    return PlanBlocker(code=type(error).__name__, reason=str(error))


class _Planner:
    """Decides each entity in install order, so later kinds see earlier choices."""

    def __init__(
        self, *, pack: ExamplePack, external: ResolvedRefs, kept: dict[Key, Adoption]
    ) -> None:
        self._pack = pack
        self._kept = kept
        self.entities: list[PlannedEntity] = []
        self.adoptions: dict[Key, Adoption] = {}
        # Item ids and names known before anything is created: adopted and external.
        self._item_ids: dict[str, uuid.UUID] = {}
        self._item_names: dict[str, str] = {}
        for (kind, pack_id, ref), found in external.items():
            if kind is EntityKind.ITEM:
                self._item_ids[f"{pack_id}:{ref}"] = found.entity_id
                self._item_names[f"{pack_id}:{ref}"] = cast("str", found.name)

    def _add(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        action: PlanAction,
        reason: str | None = None,
    ) -> None:
        self.entities.append(
            PlannedEntity(kind=kind, ref=ref, label=label, action=action, reason=reason)
        )

    def _take_back(self, kind: EntityKind, ref: str, label: str) -> Adoption | None:
        """Plan to take back what an earlier install kept, if there is one."""
        adoption = self._kept.get((kind, ref))
        if adoption is None:
            return None
        self.adoptions[kind, ref] = adoption
        self._add(kind, ref, label, PlanAction.UNCHANGED, _TAKEN_BACK)
        return adoption

    def presets(self, existing: list[bool]) -> None:
        """An identical preset the person has is used, not created."""
        for spec, exists in zip(self._pack.presets, existing, strict=True):
            if exists:
                self._add(
                    EntityKind.PRESET,
                    spec.ref,
                    spec.label,
                    PlanAction.UNCHANGED,
                    _PRESET_EXISTS,
                )
            else:
                self._add(EntityKind.PRESET, spec.ref, spec.label, PlanAction.CREATE)

    async def types(self, targets: RemovalTargets) -> list[SlugClashError]:
        """Plan the relationship and item types; a taken slug is a conflict.

        The clashes are returned item types first, the order installs refused them in
        before there was a plan.
        """
        types = [
            (
                EntityKind.RELATIONSHIP_TYPE,
                r.ref,
                r.label,
                r.slug,
                "a relationship type",
            )
            for r in self._pack.relationship_types
        ] + [
            (EntityKind.ITEM_TYPE, t.ref, t.label, t.slug, "an item type")
            for t in self._pack.item_types
        ]
        clashes: dict[EntityKind, list[SlugClashError]] = {}
        for kind, ref, label, slug, noun in types:
            if self._take_back(kind, ref, label) is not None:
                continue
            if await targets.graph.slug_taken(kind, slug):
                clash = SlugClashError(kind=noun, slug=slug)
                clashes.setdefault(kind, []).append(clash)
                self._add(kind, ref, label, PlanAction.CONFLICT, str(clash))
            else:
                self._add(kind, ref, label, PlanAction.CREATE)
        return clashes.get(EntityKind.ITEM_TYPE, []) + clashes.get(
            EntityKind.RELATIONSHIP_TYPE, []
        )

    def items(self) -> None:
        for spec in self._pack.items:
            adoption = self._take_back(EntityKind.ITEM, spec.ref, spec.name)
            if adoption is not None:
                self._item_ids[spec.ref] = adoption.record.entity_id
                self._item_names[spec.ref] = adoption.content["name"]
            else:
                self._item_names[spec.ref] = spec.name
                self._add(EntityKind.ITEM, spec.ref, spec.name, PlanAction.CREATE)

    def connections(self) -> None:
        """A kept connection is taken back only if it still joins the same items."""
        for n, spec in enumerate(self._pack.connections):
            ref = f"connection-{n}"
            # A required pack's item has no name here when that pack is missing.
            source = self._item_names.get(spec.source_ref, spec.source_ref)
            target = self._item_names.get(spec.target_ref, spec.target_ref)
            label = f"{source} to {target}"
            kept = self._kept.get((EntityKind.CONNECTION, ref))
            source_id = self._item_ids.get(spec.source_ref)
            target_id = self._item_ids.get(spec.target_ref)
            if (
                kept is not None
                and kept.content["source_id"] == str(source_id)
                and kept.content["target_id"] == str(target_id)
            ):
                self._take_back(EntityKind.CONNECTION, ref, label)
            else:
                self._add(EntityKind.CONNECTION, ref, label, PlanAction.CREATE)

    def collections(self) -> None:
        for spec in self._pack.collections:
            if self._take_back(EntityKind.COLLECTION, spec.ref, spec.name) is None:
                self._add(EntityKind.COLLECTION, spec.ref, spec.name, PlanAction.CREATE)

    async def covers(self, styles: dict[str, str], covers: CoverTarget) -> None:
        """Plan a cover for each item whose type has a style.

        A kept cover comes back only with its adopted item, and an adopted item that
        already has a cover of the person's own gets none, so it is not listed.
        """
        for spec in self._pack.items:
            if spec.type_ref not in styles:
                continue
            name = self._item_names[spec.ref]
            if (EntityKind.ITEM, spec.ref) in self.adoptions:
                if self._take_back(EntityKind.COVER, spec.ref, name) is not None:
                    continue
                if await covers.has_cover(self._item_ids[spec.ref]):
                    continue
            self._add(EntityKind.COVER, spec.ref, name, PlanAction.CREATE)


async def _kept(
    pack: ExamplePack,
    cover_styles: dict[str, str],
    runs: RunRepository,
    scope: ContentFilter,
    targets: RemovalTargets,
) -> dict[Key, Adoption]:
    """Return what the installer's earlier installs kept that still fits."""
    kept = adoptable_records(await runs.list_for_bundle(pack.id, scope=scope))
    slugs: dict[Key, str | None] = {
        (EntityKind.RELATIONSHIP_TYPE, r.ref): slugify(r.slug)
        for r in pack.relationship_types
    }
    slugs |= {(EntityKind.ITEM_TYPE, t.ref): t.slug for t in pack.item_types}
    slugs |= {(EntityKind.ITEM, i.ref): None for i in pack.items}
    slugs |= {
        (EntityKind.CONNECTION, f"connection-{n}"): None
        for n in range(len(pack.connections))
    }
    slugs |= {(EntityKind.COLLECTION, c.ref): None for c in pack.collections}
    slugs |= {
        (EntityKind.COVER, i.ref): None
        for i in pack.items
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


async def _cover_styles(pack: ExamplePack, catalogue: PackCatalogue) -> dict[str, str]:
    """Return cover styles by item type ref, including required packs' types."""
    styles = _own_cover_styles(pack)
    for required in pack.requires:
        # The catalogue validates that every required pack exists.
        base = cast("ExamplePack", await catalogue.get(required))
        styles |= {
            f"{required}:{ref}": style for ref, style in _own_cover_styles(base).items()
        }
    return styles


def _own_cover_styles(pack: ExamplePack) -> dict[str, str]:
    """Return the cover style of each item type (by ref) that declares one."""
    return {t.ref: t.cover.style for t in pack.item_types if t.cover is not None}
