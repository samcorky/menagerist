from typing import TYPE_CHECKING

from app.modules.backup.domain.errors import RestoreTargetNotEmptyError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.ports.archive_member import ArchiveMember


class InMemoryDatabaseRestorer:
    """Atomic buffered replacement for tests without a database."""

    def __init__(self, revision: str) -> None:
        self._revision = revision
        self.tables: dict[str, bytes] = {}

    async def schema_revision(self) -> str:
        """Return the configured target revision."""
        return self._revision

    async def is_empty(self) -> bool:
        """Return whether any buffered table contains rows."""
        return not any(self.tables.values())

    async def restore_instance(
        self,
        members: AsyncIterator[ArchiveMember],
        *,
        replace: bool,
        setup_only: bool,
    ) -> None:
        """Publish restored members only after consuming the entire stream."""
        if (setup_only or not replace) and not await self.is_empty():
            raise RestoreTargetNotEmptyError("The restore target is not empty.")
        pending = {
            member.name: b"".join([chunk async for chunk in member.chunks])
            async for member in members
        }
        self.tables = pending
