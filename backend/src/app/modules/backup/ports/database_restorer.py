from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.ports.archive_member import ArchiveMember


class DatabaseRestorer(Protocol):
    """Transactional instance restore into the live schema."""

    async def schema_revision(self) -> str:
        """Return the target database's current migration revision."""
        ...

    async def is_empty(self) -> bool:
        """Check for instance content, ignoring builtin presets."""
        ...

    async def restore_instance(
        self,
        members: AsyncIterator[ArchiveMember],
        *,
        replace: bool,
        setup_only: bool,
    ) -> None:
        """Restore atomically, taking the setup lock when requested."""
        ...
