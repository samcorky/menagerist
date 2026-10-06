from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.examples.domain.installation import Installation


class InstallationRepository(Protocol):
    """Access to installation records, independent of storage backend."""

    async def add(self, installation: Installation) -> None:
        """Add a new installation."""
        ...

    async def save(self, installation: Installation) -> None:
        """Persist changes to an existing installation."""
        ...

    async def get(self, installation_id: uuid.UUID) -> Installation | None:
        """Return the installation with `installation_id`, or `None`."""
        ...

    async def get_active_for_pack(self, pack_id: str) -> Installation | None:
        """Return the installing or installed installation of `pack_id`, if any."""
        ...

    async def list_active(self) -> list[Installation]:
        """Return every installing or installed installation."""
        ...
