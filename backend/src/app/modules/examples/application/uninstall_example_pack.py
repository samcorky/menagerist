from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.examples.application.removal import KeptEntity, settle_installation
from app.modules.examples.domain.errors import PackNotInstalledError
from app.modules.examples.domain.installation import EntityKind, Installation, Outcome
from app.modules.examples.domain.pack import PackCounts
from app.modules.examples.ports.pack_targets import (  # noqa: TC001
    GraphTarget,
    PresetTarget,
)
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
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

    :raises PackNotInstalledError: there is nothing to remove.
    """

    def __init__(
        self, uow: ExampleUnitOfWork, presets: PresetTarget, graph: GraphTarget
    ) -> None:
        super().__init__(uow)
        self._presets = presets
        self._graph = graph

    async def handle(
        self,
        command: UninstallExamplePackCommand,
        actor: Actor,
    ) -> UninstallResult:
        """Settle every owned entity, then close the installation."""
        async with self._uow as repos:
            installation = await repos.installations.get_active_for_pack(
                command.pack_id
            )
        if installation is None:
            raise PackNotInstalledError(f"'{command.pack_id}' is not installed")

        kept = await settle_installation(
            installation,
            presets=self._presets,
            graph=self._graph,
            persist=self._persist,
        )
        installation.mark_removed()
        await self._persist(installation)
        logger.info("example pack removed", pack_id=command.pack_id, kept=len(kept))
        return UninstallResult(
            pack_id=command.pack_id,
            removed=_removed_counts(installation),
            kept=tuple(kept),
        )

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
    )
