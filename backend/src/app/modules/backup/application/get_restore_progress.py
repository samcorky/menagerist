from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar

from app.modules.backup.domain.errors import RestoreProgressNotFoundError
from app.shared_kernel.access import Access, Public
from app.shared_kernel.cqrs import UseCase
from app.shared_kernel.progress import ProgressSnapshot

if TYPE_CHECKING:
    from app.modules.backup.ports.progress_store import ProgressStore
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

# Counted from the last write, so a finished or failed restore stays readable
# for a while after the setup gate has closed.
RESTORE_PROGRESS_MAX_AGE = timedelta(minutes=10)


@dataclass(frozen=True, kw_only=True)
class GetRestoreProgressQuery:
    """Ask how the most recent restore is getting on."""


class GetRestoreProgress(UseCase[GetRestoreProgressQuery, ProgressSnapshot]):
    """Report a restore's progress to the first-run page.

    Public on purpose: the person watching has no account yet, and the gate that
    protects the restore itself closes the moment the restore commits, while the
    page still needs the final state. The snapshot holds only counts, phase
    labels and a short failure message, and expires.
    """

    access: ClassVar[Access] = Public()

    def __init__(self, store: ProgressStore, guard: AccessGuard) -> None:
        self._guard = guard
        self._store = store

    async def _handle(
        self, request: GetRestoreProgressQuery, actor: Actor
    ) -> ProgressSnapshot:
        snapshot = await self._store.read(max_age=RESTORE_PROGRESS_MAX_AGE)
        if snapshot is None:
            raise RestoreProgressNotFoundError("No restore is in progress.")
        return snapshot
