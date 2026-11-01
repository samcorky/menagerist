from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.backup.application.permissions import BackupPermission
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class PruneUserExportsCommand:
    """Expire downloadable exports on the configured retention."""


class PruneUserExports(UseCase[PruneUserExportsCommand, list[str]]):
    """Remove expired exports across owners, leaving instance backups untouched."""

    access: ClassVar[Access] = Requires(BackupPermission.DELETE)

    def __init__(
        self,
        store: BackupStore,
        guard: AccessGuard,
        *,
        user_export_ttl_hours: int = 24,
    ) -> None:
        self._guard = guard
        self._store = store
        self._ttl = timedelta(hours=user_export_ttl_hours)

    async def _handle(
        self, request: PruneUserExportsCommand, actor: Actor
    ) -> list[str]:
        removed = await self._store.cleanup_user_exports(
            before=datetime.now(UTC) - self._ttl, dry_run=False
        )
        logger.info("user exports pruned", actor_id=actor.id, removed=len(removed))
        return removed
