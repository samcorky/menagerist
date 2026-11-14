import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn, cast

import structlog

from app.modules.examples.application.install_plan import (
    Adoption,
    InstallPlan,
    plan_install,
)
from app.modules.examples.application.pack_links import apply_links
from app.modules.examples.application.permissions import ExamplePermission
from app.modules.examples.application.reported_kept import reported_kept
from app.modules.examples.domain.errors import InstallFailedError, PackNotFoundError
from app.modules.examples.domain.pack import ExamplePack, PackCounts
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.modules.transfer.application.content_hash import content_hash
from app.modules.transfer.application.removal import RemovalTargets, settle_run
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import PlanAction
from app.modules.transfer.domain.run import Run, RunStatus
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.modules.examples.application.external_refs import ResolvedRefs
    from app.modules.examples.ports.cover_target import CoverTarget
    from app.modules.transfer.ports.targets import (
        CollectionTarget,
        GraphTarget,
        PresetTarget,
    )
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


@dataclass(kw_only=True)
class InstallExamplePackCommand:
    """Request to install a shipped example pack."""

    pack_id: str


@dataclass(kw_only=True, frozen=True, eq=False)
class InstallResult:
    """What an install created, and what it took back from an earlier install."""

    pack_id: str
    created: PackCounts
    adopted: PackCounts
    linked: int = 0


@dataclass(kw_only=True)
class _Run:
    """State shared by the install steps."""

    pack: ExamplePack
    plan: InstallPlan
    installation: Run
    preset_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    type_slugs: dict[str, str] = field(default_factory=dict)
    relationship_slugs: dict[str, str] = field(default_factory=dict)
    item_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    item_names: dict[str, str] = field(default_factory=dict)
    adopted: set[tuple[EntityKind, str]] = field(default_factory=set)

    def adoption(self, kind: EntityKind, ref: str) -> Adoption | None:
        """The kept entity the plan takes back for `kind` and `ref`, if any."""
        if self.plan.action(kind, ref) is not PlanAction.UNCHANGED:
            return None
        return self.plan.adoptions.get((kind, ref))


class InstallExamplePack(
    CommandHandler[ExampleUnitOfWork, InstallExamplePackCommand, InstallResult]
):
    """Plan the install, apply the plan as ordered steps, then settle the run.

    The plan (`plan_install`, also the dry run) checks everything before the first
    write. Applying records every entity as it is made, so a failure part-way can be
    undone; settling marks the run installed and makes its links.

    Entities an earlier removal kept (edited, in use, or holding the user's data)
    and that are still live are adopted rather than created again. They are
    recorded with their original content hash, so an edit still counts as an edit.

    Installs are per person, and so are the item and relationship types they create:
    two people who install the same pack each get their own copy.

    Raises:
        PackNotFoundError: the catalogue has no such pack.
        PackAlreadyInstalledError: installed already, or an earlier install is
            unfinished.
        RequirementsNotMetError: an add-on's required pack is not installed, or no
            longer has something the add-on refers to (nothing is created).
        SlugClashError: a type slug the pack needs is taken by something that is
            not an example the pack kept earlier (nothing is created).
        InstallFailedError: a step failed; what had been created was removed.
    """

    access: ClassVar[Access] = Content(ExamplePermission.PACK_INSTALL)

    def __init__(
        self,
        uow: ExampleUnitOfWork,
        guard: AccessGuard,
        catalogue: PackCatalogue,
        presets: PresetTarget,
        graph: GraphTarget,
        collections: CollectionTarget,
        covers: CoverTarget,
    ) -> None:
        """Initialise with the unit of work, policy, catalogue and four targets."""
        super().__init__(uow, guard)
        self._catalogue = catalogue
        self._presets = presets
        self._graph = graph
        self._collections = collections
        self._covers = covers
        self._targets = RemovalTargets(
            presets=presets,
            graph=graph,
            collections=collections,
            others={EntityKind.COVER: covers},
        )

    async def _handle(
        self, command: InstallExamplePackCommand, actor: Actor
    ) -> InstallResult:
        """Install the pack and return what was created."""
        pack = await self._catalogue.get(command.pack_id)
        if pack is None:
            raise PackNotFoundError(f"Example pack '{command.pack_id}' not found")
        scope = self.scope(actor)
        async with self._uow as repos:
            plan = await plan_install(
                pack,
                runs=repos.runs,
                scope=scope,
                catalogue=self._catalogue,
                targets=self._targets,
                covers=self._covers,
            )
        if plan.errors:
            raise plan.errors[0]
        run = await self._apply(plan, actor)
        return await self._settle(run, scope)

    async def _apply(self, plan: InstallPlan, actor: Actor) -> _Run:
        """Create or take back each entity as the plan says, recording each one."""
        installation = Run.start(plan.pack.id, actor.id)
        await self._persist(installation, new=True)
        run = _Run(pack=plan.pack, plan=plan, installation=installation)
        _seed_external(run, plan.external)
        try:
            await self._install_presets(run)
            await self._install_relationship_types(run)
            await self._install_item_types(run)
            await self._install_items(run)
            await self._install_connections(run)
            await self._install_collections(run)
            await self._install_covers(run)
        except Exception as exc:
            await self._roll_back(installation, exc)
        return run

    async def _settle(self, run: _Run, scope: ContentFilter) -> InstallResult:
        """Mark the run installed, make its links and report what it did."""
        installation = run.installation
        installation.mark_installed()
        await self._persist(installation)
        created = _counts(
            r.kind for r in installation.entities if (r.kind, r.ref) not in run.adopted
        )
        linked = await self._apply_links(run.pack, installation, scope)
        logger.info(
            "example pack installed",
            pack_id=run.pack.id,
            entities=len(installation.entities),
            linked=linked,
        )
        return InstallResult(
            pack_id=run.pack.id,
            created=created,
            adopted=_counts(kind for kind, _ in run.adopted),
            linked=linked,
        )

    async def _apply_links(
        self, pack: ExamplePack, installation: Run, scope: ContentFilter
    ) -> int:
        """Apply this pack's links and other packs' links that point at it."""
        async with self._uow as repos:
            active = await repos.runs.list_active(scope=scope)
        finished = {i.bundle_id: i for i in active if i.status is RunStatus.INSTALLED}
        linked = 0
        for target in pack.link_targets:
            if target in finished:
                linked += await apply_links(
                    declaring_pack=pack,
                    declaring=installation,
                    other=finished[target],
                    graph=self._graph,
                    persist=self._persist,
                )
        for other in finished.values():
            if other.id == installation.id:
                continue
            declaring_pack = await self._catalogue.get(other.bundle_id)
            if declaring_pack is not None and pack.id in declaring_pack.link_targets:
                linked += await apply_links(
                    declaring_pack=declaring_pack,
                    declaring=other,
                    other=installation,
                    graph=self._graph,
                    persist=self._persist,
                )
        return linked

    async def _persist(self, installation: Run, *, new: bool = False) -> None:
        async with self._uow as repos:
            if new:
                await repos.runs.add(installation)
            else:
                await repos.runs.save(installation)
            await self._uow.commit()

    async def _record(
        self,
        run: _Run,
        kind: EntityKind,
        ref: str,
        label: str,
        entity_id: uuid.UUID,
        content: dict[str, Any],
    ) -> None:
        run.installation.record(kind, ref, label, entity_id, content_hash(content))
        await self._persist(run.installation)

    async def _adopt(self, run: _Run, adoption: Adoption, ref: str, label: str) -> None:
        """Record a kept entity as the new install's own, with its original hash."""
        record = adoption.record
        run.installation.record(
            record.kind, ref, label, record.entity_id, record.content_hash
        )
        run.adopted.add((record.kind, ref))
        await self._persist(run.installation)

    async def _install_presets(self, run: _Run) -> None:
        outcomes = await self._presets.ensure(run.pack.presets)
        for outcome, spec in zip(outcomes, run.pack.presets, strict=True):
            run.preset_ids[outcome.ref] = outcome.entity_id
            if outcome.created:  # an identical preset that already existed is not ours
                run.installation.record(
                    EntityKind.PRESET,
                    outcome.ref,
                    spec.label,
                    outcome.entity_id,
                    content_hash(outcome.content),
                )
        # One save for the batch: `ensure` has already created every preset.
        await self._persist(run.installation)

    async def _install_relationship_types(self, run: _Run) -> None:
        for spec in run.pack.relationship_types:
            adoption = run.adoption(EntityKind.RELATIONSHIP_TYPE, spec.ref)
            if adoption is not None:
                await self._adopt(run, adoption, spec.ref, spec.label)
                continue
            created = await self._graph.create_relationship_type(spec, run.preset_ids)
            await self._record(
                run,
                EntityKind.RELATIONSHIP_TYPE,
                spec.ref,
                spec.label,
                created.entity_id,
                created.content,
            )

    async def _install_item_types(self, run: _Run) -> None:
        for spec in run.pack.item_types:
            run.type_slugs[spec.ref] = spec.slug
            adoption = run.adoption(EntityKind.ITEM_TYPE, spec.ref)
            if adoption is not None:
                await self._adopt(run, adoption, spec.ref, spec.label)
                continue
            created = await self._graph.create_item_type(spec, run.preset_ids)
            await self._record(
                run,
                EntityKind.ITEM_TYPE,
                spec.ref,
                spec.label,
                created.entity_id,
                created.content,
            )

    async def _install_items(self, run: _Run) -> None:
        for spec in run.pack.items:
            adoption = run.adoption(EntityKind.ITEM, spec.ref)
            if adoption is not None:
                run.item_ids[spec.ref] = adoption.record.entity_id
                run.item_names[spec.ref] = adoption.content["name"]
                await self._adopt(run, adoption, spec.ref, spec.name)
                continue
            created = await self._graph.create_item(
                spec, type_slug=run.type_slugs[spec.type_ref]
            )
            run.item_ids[spec.ref] = created.entity_id
            run.item_names[spec.ref] = spec.name
            await self._record(
                run,
                EntityKind.ITEM,
                spec.ref,
                spec.name,
                created.entity_id,
                created.content,
            )

    async def _install_connections(self, run: _Run) -> None:
        slugs = run.relationship_slugs | {
            t.ref: t.slug for t in run.pack.relationship_types
        }
        for n, spec in enumerate(run.pack.connections):
            source_id = run.item_ids[spec.source_ref]
            target_id = run.item_ids[spec.target_ref]
            source = run.item_names[spec.source_ref]
            target = run.item_names[spec.target_ref]
            ref = f"connection-{n}"
            # The plan takes it back only if it still joins the same items.
            adoption = run.adoption(EntityKind.CONNECTION, ref)
            if adoption is not None:
                await self._adopt(run, adoption, ref, f"{source} to {target}")
                continue
            created = await self._graph.create_connection(
                spec,
                source_id=source_id,
                target_id=target_id,
                type_slug=slugs[spec.type_ref],
            )
            await self._record(
                run,
                EntityKind.CONNECTION,
                ref,
                f"{source} to {target}",
                created.entity_id,
                created.content,
            )

    async def _install_collections(self, run: _Run) -> None:
        for spec in run.pack.collections:
            missing = [ref for ref in spec.item_refs if ref not in run.item_ids]
            if missing:
                raise InstallFailedError(
                    f"Collection '{spec.name}' names items that were not created: "
                    + ", ".join(missing)
                )
            adoption = run.adoption(EntityKind.COLLECTION, spec.ref)
            if adoption is not None:
                await self._adopt(run, adoption, spec.ref, spec.name)
                continue
            created = await self._collections.create_collection(
                spec, item_ids=[run.item_ids[ref] for ref in spec.item_refs]
            )
            await self._record(
                run,
                EntityKind.COLLECTION,
                spec.ref,
                spec.name,
                created.entity_id,
                created.content,
            )

    async def _install_covers(self, run: _Run) -> None:
        """Give every item whose type declares a cover style its cover.

        Last, so a failure in any earlier step happens before any image is
        written. The plan leaves out an adopted item that has a cover of the
        person's own, which is never replaced.
        """
        for spec in run.pack.items:
            if run.plan.action(EntityKind.COVER, spec.ref) is None:
                continue
            name = run.item_names[spec.ref]
            adoption = run.adoption(EntityKind.COVER, spec.ref)
            if adoption is not None:
                await self._adopt(run, adoption, spec.ref, name)
                continue
            style = run.plan.cover_styles[spec.type_ref]
            created = await self._covers.create(run.item_ids[spec.ref], name, style)
            await self._record(
                run,
                EntityKind.COVER,
                spec.ref,
                name,
                created.entity_id,
                created.content,
            )

    async def _roll_back(self, installation: Run, cause: Exception) -> NoReturn:
        """Remove what was created, then raise `InstallFailedError`."""
        try:
            kept = reported_kept(
                await settle_run(installation, self._targets, persist=self._persist)
            )
            installation.mark_failed()
            await self._persist(installation)
        except Exception as rollback_error:
            logger.exception(
                "example pack rollback failed", pack_id=installation.bundle_id
            )
            raise InstallFailedError(
                f"Adding '{installation.bundle_id}' failed ({cause}) and could not be "
                + f"undone ({rollback_error}). "
                + "Remove the examples from the Examples page to finish cleaning up."
            ) from cause
        outcome = (
            f"Most of it was undone, but {len(kept)} thing(s) you had changed"
            + " were kept."
            if kept
            else "Nothing was left behind."
        )
        raise InstallFailedError(
            f"Adding '{installation.bundle_id}' failed ({cause}). {outcome}"
        ) from cause


def _seed_external(run: _Run, external: ResolvedRefs) -> None:
    """Make required packs' entities usable by their `pack:ref` strings.

    They are never recorded in the installation, so this install never removes them.
    """
    for (kind, pack_id, ref), found in external.items():
        key = f"{pack_id}:{ref}"
        if kind is EntityKind.ITEM_TYPE:
            run.type_slugs[key] = cast("str", found.slug)
        elif kind is EntityKind.RELATIONSHIP_TYPE:
            run.relationship_slugs[key] = cast("str", found.slug)
        else:
            run.item_ids[key] = found.entity_id
            run.item_names[key] = cast("str", found.name)


def installation_counts(installation: Run) -> PackCounts:
    """Count an installation's recorded entities by kind, whatever their outcome."""
    return _counts(r.kind for r in installation.entities)


def _counts(kinds: Iterable[EntityKind]) -> PackCounts:
    tally = list(kinds)

    def count(kind: EntityKind) -> int:
        return tally.count(kind)

    return PackCounts(
        presets=count(EntityKind.PRESET),
        relationship_types=count(EntityKind.RELATIONSHIP_TYPE),
        item_types=count(EntityKind.ITEM_TYPE),
        items=count(EntityKind.ITEM),
        connections=count(EntityKind.CONNECTION),
        collections=count(EntityKind.COLLECTION),
    )
