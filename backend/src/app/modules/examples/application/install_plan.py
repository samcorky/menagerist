from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from app.modules.examples.application.external_refs import resolve_external_refs
from app.modules.examples.domain.errors import (
    PackAlreadyInstalledError,
    RequirementsNotMetError,
    SlugClashError,
)
from app.modules.examples.domain.pack import ExamplePack
from app.modules.transfer.application.extras import (
    BundleExtras,
    ResolvedRefs,
    find_adoptions,
)
from app.modules.transfer.application.pipeline import plan_bundle
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import ClashPolicy, Plan, PlanBlocker
from app.shared_kernel.errors import ConflictError

if TYPE_CHECKING:
    from app.modules.examples.ports.pack_catalogue import PackCatalogue
    from app.modules.transfer.application.removal import RemovalTargets
    from app.modules.transfer.ports.run_repository import RunRepository
    from app.modules.transfer.ports.targets import CoverTarget
    from app.shared_kernel.content_filter import ContentFilter


@dataclass(kw_only=True, frozen=True, eq=False)
class InstallPlan:
    """Everything an install needs, worked out before anything is written.

    `report` is what a dry run returns, and `extras` is what applying it needs
    besides the pack. `errors` are what applying the plan raises, in order, so an
    install refuses exactly what the report shows as blocking.
    """

    pack: ExamplePack
    report: Plan
    extras: BundleExtras
    errors: tuple[ConflictError, ...] = ()


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
    if await runs.get_active_for_bundle(pack.id, scope=scope) is not None:
        error = PackAlreadyInstalledError(
            f"'{pack.id}' is already installed, or an earlier install did not "
            + "finish. Remove it first."
        )
        return InstallPlan(
            pack=pack,
            report=Plan(bundle_id=pack.id, entities=(), blockers=(_blocker(error),)),
            extras=BundleExtras(),
            errors=(error,),
        )

    cover_styles = await _cover_styles(pack, catalogue)
    blocking: list[ConflictError] = []
    external: ResolvedRefs = {}
    if pack.requires:
        try:
            external = await resolve_external_refs(
                pack, await runs.list_active(scope=scope), targets.graph, catalogue
            )
        except RequirementsNotMetError as exc:
            blocking.append(exc)
    extras = BundleExtras(
        adoptions=await find_adoptions(pack, cover_styles, runs, scope, targets),
        external=external,
        blockers=tuple(_blocker(e) for e in blocking),
        cover_styles=cover_styles,
        covers=covers,
        collections=targets.collections,
    )
    report = await plan_bundle(
        pack, targets.presets, targets.graph, clash=ClashPolicy.CONFLICT, extras=extras
    )
    return InstallPlan(
        pack=pack,
        report=report,
        extras=extras,
        errors=(*blocking, *_clashes(pack, report)),
    )


def _blocker(error: ConflictError) -> PlanBlocker:
    return PlanBlocker(code=type(error).__name__, reason=str(error))


def _clashes(pack: ExamplePack, report: Plan) -> list[SlugClashError]:
    """The taken type slugs, item types first, the order installs refused them in."""
    slugs = {(EntityKind.ITEM_TYPE, t.ref): t.slug for t in pack.item_types} | {
        (EntityKind.RELATIONSHIP_TYPE, r.ref): r.slug for r in pack.relationship_types
    }
    nouns = {
        EntityKind.ITEM_TYPE: "an item type",
        EntityKind.RELATIONSHIP_TYPE: "a relationship type",
    }
    return [
        SlugClashError(kind=nouns[kind], slug=slugs[kind, e.ref])
        for kind in (EntityKind.ITEM_TYPE, EntityKind.RELATIONSHIP_TYPE)
        for e in report.conflicts
        if e.kind is kind
    ]


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
