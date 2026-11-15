from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar, NoReturn

import structlog

from app.modules.examples.application.install_plan import InstallPlan, plan_install
from app.modules.examples.application.pack_links import apply_links
from app.modules.examples.application.permissions import ExamplePermission
from app.modules.examples.application.reported_kept import reported_kept
from app.modules.examples.domain.errors import InstallFailedError, PackNotFoundError
from app.modules.examples.domain.pack import PackCounts
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.modules.transfer.application.extras import RunLedger
from app.modules.transfer.application.pipeline import apply_bundle
from app.modules.transfer.application.removal import RemovalTargets, settle_run
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.run import Run, RunStatus
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.modules.examples.domain.pack import ExamplePack
    from app.modules.transfer.ports.targets import (
        CollectionTarget,
        CoverTarget,
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
        installation, ledger = await self._apply(plan, actor)
        return await self._settle(pack, installation, ledger, scope)

    async def _apply(self, plan: InstallPlan, actor: Actor) -> tuple[Run, RunLedger]:
        """Create or take back each entity as the plan says, recording each one."""
        installation = Run.start(plan.pack.id, actor.id)
        await self._persist(installation, new=True)
        ledger = RunLedger(installation, self._persist)
        try:
            await apply_bundle(
                plan.report,
                plan.pack,
                self._presets,
                self._graph,
                extras=replace(plan.extras, ledger=ledger),
            )
        except Exception as exc:
            await self._roll_back(installation, exc)
        return installation, ledger

    async def _settle(
        self,
        pack: ExamplePack,
        installation: Run,
        ledger: RunLedger,
        scope: ContentFilter,
    ) -> InstallResult:
        """Mark the run installed, make its links and report what it did."""
        installation.mark_installed()
        await self._persist(installation)
        created = _counts(
            r.kind
            for r in installation.entities
            if (r.kind, r.ref) not in ledger.adopted_keys
        )
        linked = await self._apply_links(pack, installation, scope)
        logger.info(
            "example pack installed",
            pack_id=pack.id,
            entities=len(installation.entities),
            linked=linked,
        )
        return InstallResult(
            pack_id=pack.id,
            created=created,
            adopted=_counts(kind for kind, _ in ledger.adopted_keys),
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
