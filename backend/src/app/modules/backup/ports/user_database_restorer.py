from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from app.modules.backup.ports.archive_member import ArchiveMember


class UserDatabaseRestorer(Protocol):
    """Atomic import into an account without existing content."""

    async def schema_revision(self) -> str:
        """Return the destination migration revision."""
        ...

    async def import_user(
        self, members: AsyncIterator[ArchiveMember], *, new_owner_id: UUID
    ) -> None:
        """Consume all members before committing, stamping the destination owner."""
        ...
