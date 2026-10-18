from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.ports.archive_member import ArchiveMember


class DatabaseSnapshot(Protocol):
    """Consistent logical snapshot of the live database schema."""

    async def schema_revision(self) -> str:
        """Return the database's current migration revision."""
        ...

    def export(self) -> AsyncIterator[ArchiveMember]:
        """Yield tables in dependency order from one read-only snapshot."""
        ...
