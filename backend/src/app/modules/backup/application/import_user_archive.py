from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.backup.application.import_user_data import ImportUserDataCommand
from app.modules.backup.application.upload_backup import upload_verified_backup
from app.modules.backup.domain.backup import BackupScope
from app.modules.backup.ports.backup_store import BackupStore
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.backup.application.import_user_data import ImportUserData
    from app.modules.backup.ports.backup_workspace import BackupWorkspace
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class ImportUserArchiveCommand:
    """A portable personal archive streamed into the caller's empty account."""

    stream: AsyncIterator[bytes]


class ImportUserArchive(CommandHandler[BackupStore, ImportUserArchiveCommand, None]):
    """Stage an upload privately and remove it after the import attempt."""

    access: ClassVar[Access] = Content()

    def __init__(
        self,
        store: BackupStore,
        importer: ImportUserData,
        workspace: BackupWorkspace,
        guard: AccessGuard,
        *,
        max_upload_size: int = 8 * 1024**3,
    ) -> None:
        super().__init__(store, guard)
        self._store, self._importer, self._workspace = store, importer, workspace
        self._max_size = max_upload_size

    async def _handle(self, request: ImportUserArchiveCommand, actor: Actor) -> None:
        """Verify a private upload, import it and remove the staged archive."""
        self._guard.assert_can_view(actor, actor.id)
        uploaded = await upload_verified_backup(
            self._store,
            self._workspace,
            request.stream,
            self._max_size,
            allowed_scope=BackupScope.USER,
        )
        try:
            await self._importer.handle(
                ImportUserDataCommand(backup_id=uploaded.id), actor
            )
        finally:
            await self._store.delete(uploaded.id)
