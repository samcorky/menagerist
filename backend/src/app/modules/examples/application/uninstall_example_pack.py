from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.application.removal import (
    REMOVAL_ORDER_SHARED,
    KeptEntity,
    settle_installation,
    settle_records,
)
from app.modules.examples.application.required_by import dependants_by_pack
from app.modules.examples.domain.errors import (
    PackNotInstalledError,
    RequiredByInstalledPackError,
)
from app.modules.examples.domain.installation import (
    EntityKind,
    EntityRecord,
    Installation,
    InstallationStatus,
    Outcome,
)
from app.modules.examples.domain.pack import PackCounts
from app.modules.examples.domain.removal import KEEP_IN_USE, KEEP_SHARED
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.pack_targets import (
    CollectionTarget,
    CoverTarget,
    GraphTarget,
    PresetTarget,
    RemoveResult,
)
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UninstallExamplePackCommand:
    """Request to remove an installed example pack."""

    pack_id: str


@dataclass(kw_only=True, frozen=True, eq=False)
class UninstallResult:
    """What a removal did: how much went, and what was kept and why."""

    pack_id: str
    removed: PackCounts
    kept: tuple[KeptEntity, ...]


class UninstallExamplePack(
    CommandHandler[ExampleUnitOfWork, UninstallExamplePackCommand, UninstallResult]
):
    """Remove what a pack created and the user has not changed; keep the rest.

    Also finishes an installation an earlier crash left unfinished.

    Item and relationship types are shared structure. While another person's
    installation of the pack is active the types stay; the last person out also
    removes the types earlier uninstalls left for them, if nothing uses them.

    :raises PackNotInstalledError: there is nothing to remove.
    :raises RequiredByInstalledPackError: an installed add-on still needs the pack
        (nothing is touched).
    """

    access: ClassVar[Access] = Content()

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
        super().__init__(uow, guard)
        self._catalogue = catalogue
        self._presets = presets
        self._graph = graph
        self._collections = collections
        self._covers = covers

    async def _handle(
        self,
        command: UninstallExamplePackCommand,
        actor: Actor,
    ) -> UninstallResult:
        """Settle every owned entity, then close the installation."""
        scope = self.scope(actor)
        async with self._uow as repos:
            installation = await repos.installations.get_active_for_pack(
                command.pack_id, scope=scope
            )
            active = await repos.installations.list_active(scope=scope)
        if installation is None:
            raise PackNotInstalledError(f"'{command.pack_id}' is not installed")
        dependants = dependants_by_pack(
            await self._catalogue.list_packs(), {i.pack_id for i in active}
        ).get(command.pack_id, [])
        if dependants:
            raise RequiredByInstalledPackError(names=[d.name for d in dependants])

        link_kept = await self._settle_incoming_links(
            command.pack_id, installation, active
        )
        history = await self._pack_history(command.pack_id)
        kept = await settle_installation(
            installation,
            presets=self._presets,
            graph=self._graph,
            collections=self._collections,
            covers=self._covers,
            persist=self._persist,
            types_shared=any(
                i.is_active and i.owner_id != installation.owner_id for i in history
            ),
        )
        kept = [*link_kept, *kept]
        installation.mark_removed()
        await self._persist(installation)
        await self._release_shared_types(installation, history)
        logger.info("example pack removed", pack_id=command.pack_id, kept=len(kept))
        return UninstallResult(
            pack_id=command.pack_id,
            removed=_removed_counts(installation),
            kept=tuple(kept),
        )

    async def _settle_incoming_links(
        self, pack_id: str, removing: Installation, active: list[Installation]
    ) -> list[KeptEntity]:
        """Settle links other packs hold with `pack_id`, before its items go."""
        prefix = f"link:{pack_id}:"
        kept: list[KeptEntity] = []
        for other in active:
            if other.id == removing.id:
                continue
            records = [
                r
                for r in other.owned(EntityKind.CONNECTION)
                if r.ref.startswith(prefix)
            ]
            if records:
                kept += await settle_records(
                    other,
                    records,
                    presets=self._presets,
                    graph=self._graph,
                    collections=self._collections,
                    covers=self._covers,
                    persist=self._persist,
                )
        return kept

    async def _pack_history(self, pack_id: str) -> list[Installation]:
        async with self._uow as repos:
            # all-users check: shared structure
            return await repos.installations.list_for_pack(
                pack_id, scope=ContentFilter.everyone()
            )

    async def _release_shared_types(
        self, finished: Installation, history: list[Installation]
    ) -> None:
        """Remove types other people's removed installs left behind, if unused.

        Only once no installation of the pack is active. A type that was edited or
        is still used by anyone's content stays.
        """
        if any(i.is_active and i.id != finished.id for i in history):
            return
        others = [
            i
            for i in history
            if i.owner_id != finished.owner_id
            and i.status is InstallationStatus.REMOVED
        ]
        # Types first, then the presets they used.
        for kind in (*REMOVAL_ORDER_SHARED, EntityKind.PRESET):
            for other in others:
                for record in other.entities:
                    if (
                        record.kind is kind
                        and record.outcome is Outcome.KEPT
                        and record.reason in (KEEP_SHARED, KEEP_IN_USE)
                        and await self._release(record)
                    ):
                        other.settle_kept_as_removed(record.entity_id)
                        await self._persist(other)

    async def _release(self, record: EntityRecord) -> bool:
        """Remove the kept type if unedited and unused; whether it is now gone."""
        found = (
            await self._presets.inspect(record.entity_id)
            if record.kind is EntityKind.PRESET
            else await self._graph.inspect(record.kind, record.entity_id)
        )
        if found is None:
            return True
        if content_hash(found.content) != record.content_hash or found.still_in_use:
            return False
        if record.kind is EntityKind.PRESET:
            result = await self._presets.remove(record.entity_id)
        else:
            result = await self._graph.remove(record.kind, record.entity_id)
        return result is not RemoveResult.REFUSED_IN_USE

    async def _persist(self, installation: Installation) -> None:
        async with self._uow as repos:
            await repos.installations.save(installation)
            await self._uow.commit()


def _removed_counts(installation: Installation) -> PackCounts:
    def count(kind: EntityKind) -> int:
        return sum(
            1
            for r in installation.entities
            if r.kind is kind and r.outcome is Outcome.REMOVED
        )

    return PackCounts(
        presets=count(EntityKind.PRESET),
        relationship_types=count(EntityKind.RELATIONSHIP_TYPE),
        item_types=count(EntityKind.ITEM_TYPE),
        items=count(EntityKind.ITEM),
        connections=count(EntityKind.CONNECTION),
        collections=count(EntityKind.COLLECTION),
    )
