import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn

import structlog

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.application.removal import settle_installation
from app.modules.examples.domain.errors import (
    InstallFailedError,
    PackAlreadyInstalledError,
    PackNotFoundError,
    SlugClashError,
)
from app.modules.examples.domain.installation import EntityKind, Installation
from app.modules.examples.domain.pack import ExamplePack, PackCounts
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.pack_targets import (  # noqa: TC001
    CollectionTarget,
    GraphTarget,
    PresetTarget,
)
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class InstallExamplePackCommand:
    """Request to install a shipped example pack."""

    pack_id: str


@dataclass(kw_only=True, frozen=True, eq=False)
class InstallResult:
    """What an install created."""

    pack_id: str
    created: PackCounts


@dataclass(kw_only=True)
class _Run:
    """State shared by the install steps."""

    pack: ExamplePack
    installation: Installation
    preset_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    type_slugs: dict[str, str] = field(default_factory=dict)
    item_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    item_names: dict[str, str] = field(default_factory=dict)


class InstallExamplePack(
    CommandHandler[ExampleUnitOfWork, InstallExamplePackCommand, InstallResult]
):
    """Install a pack as ordered steps, recording every entity as it is made.

    Raises:
        PackNotFoundError: the catalogue has no such pack.
        PackAlreadyInstalledError: installed already, or an earlier install is
            unfinished.
        SlugClashError: a type slug the pack needs is taken (nothing is created).
        InstallFailedError: a step failed; what had been created was removed.
    """

    def __init__(
        self,
        uow: ExampleUnitOfWork,
        catalogue: PackCatalogue,
        presets: PresetTarget,
        graph: GraphTarget,
        collections: CollectionTarget,
    ) -> None:
        """Initialise with the unit of work, catalogue and the three targets."""
        super().__init__(uow)
        self._catalogue = catalogue
        self._presets = presets
        self._graph = graph
        self._collections = collections

    async def handle(
        self, command: InstallExamplePackCommand, actor: Actor
    ) -> InstallResult:
        """Install the pack and return what was created."""
        pack = await self._catalogue.get(command.pack_id)
        if pack is None:
            raise PackNotFoundError(f"Example pack '{command.pack_id}' not found")
        await self._check_not_installed(pack)
        await self._check_slugs(pack)

        installation = Installation.start(pack.id)
        await self._persist(installation, new=True)
        try:
            await self._run_steps(_Run(pack=pack, installation=installation))
        except Exception as exc:
            await self._roll_back(installation, exc)

        installation.mark_installed()
        await self._persist(installation)
        logger.info(
            "example pack installed",
            pack_id=pack.id,
            entities=len(installation.entities),
        )
        return InstallResult(pack_id=pack.id, created=installation_counts(installation))

    async def _check_not_installed(self, pack: ExamplePack) -> None:
        async with self._uow as repos:
            active = await repos.installations.get_active_for_pack(pack.id)
        if active is not None:
            raise PackAlreadyInstalledError(
                f"'{pack.id}' is already installed, or an earlier install did not "
                + "finish. Remove it first."
            )

    async def _check_slugs(self, pack: ExamplePack) -> None:
        for spec in pack.item_types:
            if await self._graph.slug_taken(EntityKind.ITEM_TYPE, spec.slug):
                raise SlugClashError(kind="an item type", slug=spec.slug)
        for rel in pack.relationship_types:
            if await self._graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, rel.slug):
                raise SlugClashError(kind="a relationship type", slug=rel.slug)

    async def _persist(self, installation: Installation, *, new: bool = False) -> None:
        async with self._uow as repos:
            if new:
                await repos.installations.add(installation)
            else:
                await repos.installations.save(installation)
            await self._uow.commit()

    async def _run_steps(self, run: _Run) -> None:
        await self._install_presets(run)
        await self._install_relationship_types(run)
        await self._install_item_types(run)
        await self._install_items(run)
        await self._install_connections(run)
        await self._install_collections(run)

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
            created = await self._graph.create_item_type(spec, run.preset_ids)
            run.type_slugs[spec.ref] = spec.slug
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
        slugs = {t.ref: t.slug for t in run.pack.relationship_types}
        for n, spec in enumerate(run.pack.connections):
            created = await self._graph.create_connection(
                spec,
                source_id=run.item_ids[spec.source_ref],
                target_id=run.item_ids[spec.target_ref],
                type_slug=slugs[spec.type_ref],
            )
            source = run.item_names[spec.source_ref]
            target = run.item_names[spec.target_ref]
            await self._record(
                run,
                EntityKind.CONNECTION,
                f"connection-{n}",
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

    async def _roll_back(
        self, installation: Installation, cause: Exception
    ) -> NoReturn:
        """Remove what was created, then raise `InstallFailedError`."""
        try:
            kept = await settle_installation(
                installation,
                presets=self._presets,
                graph=self._graph,
                collections=self._collections,
                persist=self._persist,
            )
            installation.mark_failed()
            await self._persist(installation)
        except Exception as rollback_error:
            logger.exception(
                "example pack rollback failed", pack_id=installation.pack_id
            )
            raise InstallFailedError(
                f"Adding '{installation.pack_id}' failed ({cause}) and could not be "
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
            f"Adding '{installation.pack_id}' failed ({cause}). {outcome}"
        ) from cause


def installation_counts(installation: Installation) -> PackCounts:
    """Count an installation's recorded entities by kind, whatever their outcome."""

    def count(kind: EntityKind) -> int:
        return sum(1 for r in installation.entities if r.kind is kind)

    return PackCounts(
        presets=count(EntityKind.PRESET),
        relationship_types=count(EntityKind.RELATIONSHIP_TYPE),
        item_types=count(EntityKind.ITEM_TYPE),
        items=count(EntityKind.ITEM),
        connections=count(EntityKind.CONNECTION),
        collections=count(EntityKind.COLLECTION),
    )
