from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.backup.application.restore_backup import (
    RESTORE_PLAN,
    restore_verified_backup,
)
from app.modules.backup.application.upload_backup import upload_verified_backup
from app.modules.backup.domain.errors import RestoreTargetNotEmptyError
from app.shared_kernel.access import Access, Public
from app.shared_kernel.cqrs import UseCase
from app.shared_kernel.progress import NULL_PROGRESS, failure_reason

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_workspace import BackupWorkspace
    from app.modules.backup.ports.database_restorer import DatabaseRestorer
    from app.modules.backup.ports.media_files import MediaFiles
    from app.modules.backup.ports.setup_gate import SetupGate
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.progress import ProgressReporter

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class RestoreOnFirstRunCommand:
    """An anonymous instance archive supplied instead of creating the first account."""

    stream: AsyncIterator[bytes]


class RestoreOnFirstRun(UseCase[RestoreOnFirstRunCommand, None]):
    """Restore accounts only while first-run setup remains open."""

    access: ClassVar[Access] = Public()

    def __init__(
        self,
        gate: SetupGate,
        store: BackupStore,
        restorer: DatabaseRestorer,
        media: MediaFiles,
        workspace: BackupWorkspace,
        guard: AccessGuard,
        *,
        max_upload_size: int = 8 * 1024**3,
        progress: ProgressReporter | None = None,
    ) -> None:
        self._gate, self._store, self._restorer = gate, store, restorer
        self._media, self._workspace = media, workspace
        self._max_size = max_upload_size
        self._guard = guard
        self._progress = progress or NULL_PROGRESS

    async def _handle(self, request: RestoreOnFirstRunCommand, actor: Actor) -> None:
        """Verify and restore only while first-run setup remains open."""
        if not await self._gate.is_open():
            raise RestoreTargetNotEmptyError("Setup has already been completed.")
        logger.warning("first-run instance restore started")
        # No caller owns this reporter, so this use case also records a failure
        # for the setup page. Starting now replaces any earlier snapshot, so a
        # rejected upload cannot leave the previous restore's state on show.
        await self._progress.begin(RESTORE_PLAN)
        try:
            uploaded = await upload_verified_backup(
                self._store, self._workspace, request.stream, self._max_size
            )
            try:
                await restore_verified_backup(
                    self._store,
                    self._restorer,
                    self._media,
                    self._workspace,
                    uploaded.id,
                    setup_only=True,
                    progress=self._progress,
                )
            finally:
                await self._store.delete(uploaded.id)
        except Exception as error:
            await self._progress.fail(failure_reason(error))
            raise
        logger.warning("first-run instance restore completed")
