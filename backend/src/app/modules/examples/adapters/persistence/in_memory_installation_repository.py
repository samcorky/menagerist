from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.examples.domain.installation import Installation
    from app.shared_kernel.content_filter import ContentFilter


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

    async def get(
        self, installation_id: uuid.UUID, *, scope: ContentFilter
    ) -> Installation | None:
        """Return the installation with `installation_id` in `scope`, or `None`."""
        found = self._installations.get(installation_id)
        return found if found is not None and scope.covers(found.owner_id) else None

    async def get_active_for_pack(
        self, pack_id: str, *, scope: ContentFilter
    ) -> Installation | None:
        """Return the installing or installed installation of `pack_id`, if any."""
        return next(
            (
                i
                for i in self._installations.values()
                if i.pack_id == pack_id and i.is_active and scope.covers(i.owner_id)
            ),
            None,
        )

    async def list_active(self, *, scope: ContentFilter) -> list[Installation]:
        """Return every installing or installed installation, oldest first."""
        return sorted(
            (
                i
                for i in self._installations.values()
                if i.is_active and scope.covers(i.owner_id)
            ),
            key=lambda i: i.id,
        )

    async def list_for_pack(
        self, pack_id: str, *, scope: ContentFilter
    ) -> list[Installation]:
        """Return every installation of `pack_id`, whatever its status, newest first."""
        return sorted(
            (
                i
                for i in self._installations.values()
                if i.pack_id == pack_id and scope.covers(i.owner_id)
            ),
            key=lambda i: i.id,
            reverse=True,
        )

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every installation with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._installations.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
