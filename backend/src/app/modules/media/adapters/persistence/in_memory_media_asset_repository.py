from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
    from app.shared_kernel.access_scope import AccessScope


class InMemoryMediaAssetRepository:
    """Dict-backed `MediaAssetRepository` for tests."""

    def __init__(self) -> None:
        self._assets: dict[uuid.UUID, MediaAsset] = {}

    def owner_of(self, asset_id: uuid.UUID) -> uuid.UUID | None:
        """Return the stored asset's owner, or `None` if absent or unowned."""
        found = self._assets.get(asset_id)
        return None if found is None else found.owner_id

    async def add(self, asset: MediaAsset) -> None:
        """Persist a new media asset."""
        self._assets[asset.id] = asset

    async def save(self, asset: MediaAsset) -> None:
        """Persist changes to an existing media asset."""
        self._assets[asset.id] = asset

    async def get(
        self, asset_id: uuid.UUID, *, scope: AccessScope
    ) -> MediaAsset | None:
        """Return the asset with `asset_id`, or `None` if missing or unseen."""
        found = self._assets.get(asset_id)
        return found if found is not None and scope.covers(found.owner_id) else None

    async def list_expired(
        self,
        *,
        status: MediaStatus,
        before: datetime,
        scope: AccessScope,
    ) -> list[MediaAsset]:
        """Return assets in `scope` and `status` last updated before `before`."""
        return [
            a
            for a in self._assets.values()
            if a.status is status and a.updated_at < before and scope.covers(a.owner_id)
        ]

    async def list_by_status(
        self, *, status: MediaStatus, scope: AccessScope
    ) -> list[MediaAsset]:
        """Return all assets in `scope` that are in `status`."""
        return [
            a
            for a in self._assets.values()
            if a.status is status and scope.covers(a.owner_id)
        ]

    async def delete(self, asset_id: uuid.UUID) -> None:
        """Hard-delete the asset record."""
        self._assets.pop(asset_id, None)

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every asset with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._assets.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
