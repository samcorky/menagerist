from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.examples.domain.installation import Installation


class InMemoryInstallationRepository:
    """Dict-backed `InstallationRepository` for tests."""

    def __init__(self) -> None:
        self._installations: dict[uuid.UUID, Installation] = {}

    async def add(self, installation: Installation) -> None:
        """Add a new installation."""
        self._installations[installation.id] = installation

    async def save(self, installation: Installation) -> None:
        """Persist changes to an existing installation."""
        self._installations[installation.id] = installation

    async def get(self, installation_id: uuid.UUID) -> Installation | None:
        """Return the installation with `installation_id`, or `None`."""
        return self._installations.get(installation_id)

    async def get_active_for_pack(self, pack_id: str) -> Installation | None:
        """Return the installing or installed installation of `pack_id`, if any."""
        return next(
            (
                i
                for i in self._installations.values()
                if i.pack_id == pack_id and i.is_active
            ),
            None,
        )

    async def list_active(self) -> list[Installation]:
        """Return every installing or installed installation, oldest first."""
        return sorted(
            (i for i in self._installations.values() if i.is_active),
            key=lambda i: i.id,
        )

    async def list_for_pack(self, pack_id: str) -> list[Installation]:
        """Return every installation of `pack_id`, whatever its status, newest first."""
        return sorted(
            (i for i in self._installations.values() if i.pack_id == pack_id),
            key=lambda i: i.id,
            reverse=True,
        )
