from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.verification import PruneReport
from app.shared_kernel.cqrs import AuthorisedUseCase
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class PruneBackupsCommand:
    """Retention overrides; an age is additional to the newest-count floor."""

    keep_last: int | None = None
    older_than: timedelta | None = None
    pre_migration_keep: int | None = None
    dry_run: bool = False


class PruneBackups(
    AuthorisedUseCase[PruneBackupsCommand, PruneReport, BackupPermission]
):
    """Prune summary-based retention groups without opening any archives."""

    required_permission = BackupPermission.DELETE

    def __init__(
        self,
        store: BackupStore,
        authorisation: AuthorisationPort,
        *,
        keep_last: int = 7,
        pre_migration_keep: int = 3,
        user_export_ttl_hours: int = 24,
    ) -> None:
        super().__init__(authorisation)
        self._store = store
        self._keep_last = keep_last
        self._pre_migration_keep = pre_migration_keep
        self._user_export_ttl = timedelta(hours=user_export_ttl_hours)

    def _limits(self, request: PruneBackupsCommand) -> tuple[int, int]:
        ordinary = self._keep_last if request.keep_last is None else request.keep_last
        migration = (
            self._pre_migration_keep
            if request.pre_migration_keep is None
            else request.pre_migration_keep
        )
        if request.older_than is not None:
            if request.older_than < timedelta(0):
                raise ValidationError("Backup retention age cannot be negative.")
            if request.keep_last is None:
                ordinary = 1
            if request.pre_migration_keep is None:
                migration = 1
        if ordinary < 0 or migration < 0:
            raise ValidationError("Backup retention counts cannot be negative.")
        return max(1, ordinary), max(1, migration)

    async def _handle(self, request: PruneBackupsCommand, actor: Actor) -> PruneReport:
        ordinary, migration = self._limits(request)
        summaries = await self._store.list()
        now = datetime.now(UTC)
        deleted: list[str] = []
        kept: list[str] = []
        freed = 0
        for pre_migration, count in ((False, ordinary), (True, migration)):
            group = sorted(
                (
                    item
                    for item in summaries
                    if (item.label == "pre-migration") == pre_migration
                ),
                key=lambda item: (item.created_at, item.id),
                reverse=True,
            )
            for position, summary in enumerate(group):
                old_enough = (
                    request.older_than is None
                    or summary.created_at < now - request.older_than
                )
                if position < count or not old_enough:
                    kept.append(str(summary.id))
                    continue
                if not request.dry_run:
                    await self._store.delete(summary.id)
                deleted.append(str(summary.id))
                freed += summary.size
        unreadable = await self._store.unreadable()
        orphans = await self._store.cleanup_orphans(
            before=now - timedelta(hours=1), dry_run=request.dry_run
        )
        user_exports = await self._store.cleanup_user_exports(
            before=now - self._user_export_ttl, dry_run=request.dry_run
        )
        report = PruneReport(
            deleted=deleted,
            kept=kept,
            freed_bytes=freed,
            orphans_removed=orphans,
            unreadable=unreadable,
            user_exports_removed=user_exports,
        )
        logger.info(
            "instance backups pruned",
            actor_id=actor.id,
            deleted=len(deleted),
            freed_bytes=freed,
            dry_run=request.dry_run,
        )
        return report
