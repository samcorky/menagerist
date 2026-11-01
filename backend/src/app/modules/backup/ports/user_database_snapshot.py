from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.modules.backup.ports.archive_member import ArchiveMember
    from app.shared_kernel.content_filter import ContentFilter


class UserDatabaseSnapshot(Protocol):
    """A person's content and the shared vocabulary it requires."""

    async def schema_revision(self) -> str:
        """Return the source migration revision."""
        ...

    def export(self, *, scope: ContentFilter) -> AsyncGenerator[ArchiveMember]:
        """Export only content in one owner's scope."""
        ...
