from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.examples.domain.installation import Installation
    from app.shared_kernel.content_filter import ContentFilter


class InstallationRepository(Protocol):
    """Access to installation records, independent of storage backend."""

    async def add(self, installation: Installation) -> None:
        """Add a new installation."""
        ...

    async def save(self, installation: Installation) -> None:
        """Persist changes to an existing installation."""
        ...

    async def get(
        self, installation_id: uuid.UUID, *, scope: ContentFilter
    ) -> Installation | None:
        """Return the installation with `installation_id`, or `None`."""
        ...

    async def get_active_for_pack(
        self, pack_id: str, *, scope: ContentFilter
    ) -> Installation | None:
        """Return the installing or installed installation of `pack_id`, if any."""
        ...

    async def list_active(self, *, scope: ContentFilter) -> list[Installation]:
        """Return every installing or installed installation."""
        ...

    async def list_for_pack(
        self, pack_id: str, *, scope: ContentFilter
    ) -> list[Installation]:
        """Return every installation of `pack_id`, whatever its status, newest first."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every installation with no owner or a legacy owner.

        System-level and unscoped, deleted rows included. Returns the count.
        """
        ...
