from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.examples.application.permissions import ExamplePermission
from app.modules.examples.application.removal import (
    KeptEntity,
    settle_installation,
    settle_records,
)
from app.modules.examples.application.required_by import dependants_by_pack
from app.modules.examples.domain.errors import (
    PackNotInstalledError,
    RequiredByInstalledPackError,
)
from app.modules.examples.domain.installation import Installation, Outcome
from app.modules.examples.domain.pack import PackCounts
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.modules.transfer.domain.entity_kind import EntityKind

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.transfer.ports.targets import (  # noqa: TC001
    CollectionTarget,
    GraphTarget,
    PresetTarget,
)
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.examples.ports.cover_target import CoverTarget
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

    Item and relationship types and choice lists belong to the person who
    installed the pack, so removal never touches anyone else's copy.

    :raises PackNotInstalledError: there is nothing to remove.
    :raises RequiredByInstalledPackError: an installed add-on still needs the pack
        (nothing is touched).
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
        kept = await settle_installation(
            installation,
            presets=self._presets,
            graph=self._graph,
            collections=self._collections,
            covers=self._covers,
            persist=self._persist,
        )
        kept = [*link_kept, *kept]
        installation.mark_removed()
        await self._persist(installation)
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
