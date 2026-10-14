import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn, cast

import structlog

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.application.external_refs import (
    ResolvedRefs,
    resolve_external_refs,
)
from app.modules.examples.application.pack_links import apply_links
from app.modules.examples.application.removal import inspect_record, settle_installation
from app.modules.examples.domain.errors import (
    InstallFailedError,
    PackAlreadyInstalledError,
    PackNotFoundError,
    SlugClashError,
)
from app.modules.examples.domain.installation import (
    EntityKind,
    EntityRecord,
    Installation,
    InstallationStatus,
    adoptable_records,
)
from app.modules.examples.domain.pack import ExamplePack, PackCounts
from app.modules.examples.domain.removal import holds_shared_type
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.pack_targets import (  # noqa: TC001
    CollectionTarget,
    CoverTarget,
    GraphTarget,
    PresetTarget,
)
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.cqrs import ScopedCommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.shared_kernel.access_policy import AccessPolicy
    from app.shared_kernel.actor import Actor

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


_Key = tuple[EntityKind, str]


@dataclass(kw_only=True, frozen=True, eq=False)
class _Adoption:
    """An entity a pack kept earlier that is still live, and as it is now."""

    record: EntityRecord
    content: dict[str, Any]


@dataclass(kw_only=True)
class _Run:
    """State shared by the install steps."""

    pack: ExamplePack
    installation: Installation
    preset_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    type_slugs: dict[str, str] = field(default_factory=dict)
    relationship_slugs: dict[str, str] = field(default_factory=dict)
    cover_styles: dict[str, str] = field(default_factory=dict)
    item_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    item_names: dict[str, str] = field(default_factory=dict)
    adoptions: dict[_Key, _Adoption] = field(default_factory=dict)
    adopted: set[_Key] = field(default_factory=set)
    reused: set[_Key] = field(default_factory=set)


class InstallExamplePack(
    ScopedCommandHandler[ExampleUnitOfWork, InstallExamplePackCommand, InstallResult]
):
    """Install a pack as ordered steps, recording every entity as it is made.

    Entities an earlier removal kept (edited, in use, or holding the user's data)
    and that are still live are adopted rather than created again. They are
    recorded with their original content hash, so an edit still counts as an edit.

    Installs are per person. Item and relationship types are shared structure: one
    that another person's installation of the same pack created is reused, never
    recorded here and so never removed by this person's uninstall.

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

    def __init__(
        self,
        uow: ExampleUnitOfWork,
        policy: AccessPolicy,
        catalogue: PackCatalogue,
        presets: PresetTarget,
        graph: GraphTarget,
        collections: CollectionTarget,
        covers: CoverTarget,
    ) -> None:
        """Initialise with the unit of work, policy, catalogue and four targets."""
        super().__init__(uow, policy)
        self._catalogue = catalogue
        self._presets = presets
        self._graph = graph
        self._collections = collections
        self._covers = covers

    async def handle(
        self, command: InstallExamplePackCommand, actor: Actor
    ) -> InstallResult:
        """Install the pack and return what was created."""
        pack = await self._catalogue.get(command.pack_id)
        if pack is None:
            raise PackNotFoundError(f"Example pack '{command.pack_id}' not found")
        scope = self._policy.scope_for(actor)
        await self._check_not_installed(pack, scope)
        external = await self._resolve_external(pack, scope, actor.id)
        cover_styles = await self._cover_styles(pack)
        adoptions = await self._find_adoptions(pack, cover_styles, scope)
        reused = await self._check_slugs(pack, adoptions, actor)

        installation = Installation.start(pack.id, actor.id)
        await self._persist(installation, new=True)
        run = _Run(
            pack=pack,
            installation=installation,
            adoptions=adoptions,
            reused=reused,
            cover_styles=cover_styles,
        )
        _seed_external(run, external)
        try:
            await self._run_steps(run)
        except Exception as exc:
            await self._roll_back(installation, exc)

        installation.mark_installed()
        await self._persist(installation)
        created = _counts(
            r.kind for r in installation.entities if (r.kind, r.ref) not in run.adopted
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
            adopted=_counts(kind for kind, _ in run.adopted),
            linked=linked,
        )

    async def _apply_links(
        self, pack: ExamplePack, installation: Installation, scope: AccessScope
    ) -> int:
        """Apply this pack's links and other packs' links that point at it."""
        async with self._uow as repos:
            active = await repos.installations.list_active(scope=scope)
        finished = {
            i.pack_id: i for i in active if i.status is InstallationStatus.INSTALLED
        }
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
            declaring_pack = await self._catalogue.get(other.pack_id)
            if declaring_pack is not None and pack.id in declaring_pack.link_targets:
                linked += await apply_links(
                    declaring_pack=declaring_pack,
                    declaring=other,
                    other=installation,
                    graph=self._graph,
                    persist=self._persist,
                )
        return linked

    async def _check_not_installed(self, pack: ExamplePack, scope: AccessScope) -> None:
        async with self._uow as repos:
            active = await repos.installations.get_active_for_pack(pack.id, scope=scope)
        if active is not None:
            raise PackAlreadyInstalledError(
                f"'{pack.id}' is already installed, or an earlier install did not "
                + "finish. Remove it first."
            )

    async def _resolve_external(
        self, pack: ExamplePack, scope: AccessScope, actor_id: uuid.UUID
    ) -> ResolvedRefs:
        """Resolve the add-on's references to required packs, before anything exists.

        Only the installer's own installations count.
        """
        if not pack.requires:
            return {}
        async with self._uow as repos:
            active = await repos.installations.list_active(scope=scope)
            others = [
                i
                for pack_id in pack.requires
                # all-users check: shared structure
                for i in await repos.installations.list_for_pack(
                    pack_id, scope=AccessScope.everyone()
                )
                if i.owner_id != actor_id
            ]
        return await resolve_external_refs(
            pack, active, self._graph, self._catalogue, others
        )

    async def _cover_styles(self, pack: ExamplePack) -> dict[str, str]:
        """Return cover styles by item type ref, including required packs' types."""
        styles = _own_cover_styles(pack)
        for required in pack.requires:
            # The catalogue validates that every required pack exists.
            base = cast("ExamplePack", await self._catalogue.get(required))
            styles |= {
                f"{required}:{ref}": style
                for ref, style in _own_cover_styles(base).items()
            }
        return styles

    async def _find_adoptions(
        self, pack: ExamplePack, cover_styles: dict[str, str], scope: AccessScope
    ) -> dict[_Key, _Adoption]:
        """Return what the installer's earlier installs kept that still fits."""
        async with self._uow as repos:
            history = await repos.installations.list_for_pack(pack.id, scope=scope)
        kept = adoptable_records(history)
        slugs: dict[_Key, str | None] = {
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
        slugs |= {(EntityKind.COVER, ref): None for ref in _covered(pack, cover_styles)}

        adoptions: dict[_Key, _Adoption] = {}
        for key, expected_slug in slugs.items():
            record = kept.get(key)
            if record is None:
                continue
            inspection = await inspect_record(
                record,
                presets=self._presets,
                graph=self._graph,
                collections=self._collections,
                covers=self._covers,
            )
            if inspection is None:
                continue
            if (
                expected_slug is not None
                and inspection.content["slug"] != expected_slug
            ):
                continue
            adoptions[key] = _Adoption(record=record, content=inspection.content)
        return adoptions

    async def _check_slugs(
        self, pack: ExamplePack, adoptions: dict[_Key, _Adoption], actor: Actor
    ) -> set[_Key]:
        """Refuse a taken type slug unless another person's install created it.

        Returns the keys of the shared types to reuse.
        """
        reused: set[_Key] = set()
        types = [
            (EntityKind.ITEM_TYPE, spec.ref, spec.slug, "an item type")
            for spec in pack.item_types
        ] + [
            (EntityKind.RELATIONSHIP_TYPE, rel.ref, rel.slug, "a relationship type")
            for rel in pack.relationship_types
        ]
        others: list[Installation] | None = None
        for kind, ref, slug, noun in types:
            if (kind, ref) in adoptions:
                continue
            if not await self._graph.slug_taken(kind, slug):
                continue
            if others is None:
                others = await self._others_installations(pack.id, actor)
            expected = slug if kind is EntityKind.ITEM_TYPE else slugify(slug)
            if await self._shared_by(others, kind, ref, expected):
                reused.add((kind, ref))
                continue
            raise SlugClashError(kind=noun, slug=slug)
        return reused

    async def _others_installations(
        self, pack_id: str, actor: Actor
    ) -> list[Installation]:
        async with self._uow as repos:
            # all-users check: shared structure
            everyone = await repos.installations.list_for_pack(
                pack_id, scope=AccessScope.everyone()
            )
        return [i for i in everyone if i.owner_id != actor.id]

    async def _shared_by(
        self, others: list[Installation], kind: EntityKind, ref: str, slug: str
    ) -> bool:
        """Whether another person's install of this pack holds a live type `slug`.

        Held means owned by an active install, or kept (shared or in use) by one
        that has since been removed.
        """
        for installation in others:
            for record in installation.entities:
                if (record.kind, record.ref) != (kind, ref):
                    continue
                if not holds_shared_type(installation, record):
                    continue
                found = await self._graph.inspect(kind, record.entity_id)
                if found is not None and found.content["slug"] == slug:
                    return True
        return False

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
        await self._install_covers(run)

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

    async def _adopt(
        self, run: _Run, adoption: _Adoption, ref: str, label: str
    ) -> None:
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
            if (EntityKind.RELATIONSHIP_TYPE, spec.ref) in run.reused:
                continue
            adoption = run.adoptions.get((EntityKind.RELATIONSHIP_TYPE, spec.ref))
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
            if (EntityKind.ITEM_TYPE, spec.ref) in run.reused:
                continue
            adoption = run.adoptions.get((EntityKind.ITEM_TYPE, spec.ref))
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
            adoption = run.adoptions.get((EntityKind.ITEM, spec.ref))
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
            adoption = run.adoptions.get((EntityKind.CONNECTION, ref))
            # Only if it still joins the items this run uses.
            if adoption is not None and (
                adoption.content["source_id"] == str(source_id)
                and adoption.content["target_id"] == str(target_id)
            ):
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
            adoption = run.adoptions.get((EntityKind.COLLECTION, spec.ref))
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
        written. A kept cover comes back only with its adopted item, and an
        adopted item that already has a cover of the person's own gets none.
        """
        styles = run.cover_styles
        for spec in run.pack.items:
            style = styles.get(spec.type_ref)
            if style is None:
                continue
            name = run.item_names[spec.ref]
            was_adopted = (EntityKind.ITEM, spec.ref) in run.adopted
            adoption = run.adoptions.get((EntityKind.COVER, spec.ref))
            if adoption is not None and was_adopted:
                await self._adopt(run, adoption, spec.ref, name)
                continue
            # The person's own cover is never replaced.
            if was_adopted and await self._covers.has_cover(run.item_ids[spec.ref]):
                continue
            created = await self._covers.create(run.item_ids[spec.ref], name, style)
            await self._record(
                run,
                EntityKind.COVER,
                spec.ref,
                name,
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
                covers=self._covers,
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


def _own_cover_styles(pack: ExamplePack) -> dict[str, str]:
    """Return the cover style of each item type (by ref) that declares one."""
    return {t.ref: t.cover.style for t in pack.item_types if t.cover is not None}


def _covered(pack: ExamplePack, styles: dict[str, str]) -> list[str]:
    """Return the refs of the items that get a cover."""
    return [i.ref for i in pack.items if i.type_ref in styles]


def installation_counts(installation: Installation) -> PackCounts:
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
