"""Write a running import's progress to its row, for its owner to watch."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.transfer.application.stored_imports import (
    RecordItemImportProgressCommand,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from app.modules.transfer.application.stored_imports import RecordItemImportProgress
    from app.shared_kernel.progress import ProgressSnapshot


class ItemImportProgressSink:
    """Each snapshot is its own short transaction, apart from the import's own."""

    def __init__(
        self, record: Callable[[], RecordItemImportProgress], import_id: uuid.UUID
    ) -> None:
        self._record = record
        self._import_id = import_id

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Keep the snapshot on the import."""
        await self._record().handle(
            RecordItemImportProgressCommand(
                import_id=self._import_id, snapshot=snapshot, now=datetime.now(UTC)
            ),
            SYSTEM_ACTOR,
        )
