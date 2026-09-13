from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.media.domain.media_asset import MediaAsset, MediaStatus


class InMemoryMediaAssetRepository:
    """Dict-backed `MediaAssetRepository` for tests."""

    def __init__(self) -> None:
        self._assets: dict[uuid.UUID, MediaAsset] = {}

    async def add(self, asset: MediaAsset) -> None:
        """Persist a new media asset."""
        self._assets[asset.id] = asset

    async def save(self, asset: MediaAsset) -> None:
        """Persist changes to an existing media asset."""
        self._assets[asset.id] = asset

    async def get(self, asset_id: uuid.UUID) -> MediaAsset | None:
        """Return the asset with `asset_id`, or `None` if it does not exist."""
        return self._assets.get(asset_id)

    async def list_expired(
        self,
        *,
        status: MediaStatus,
        before: datetime,
    ) -> list[MediaAsset]:
        """Return assets in `status` whose `updated_at` is before `before`."""
        return [
            a
            for a in self._assets.values()
            if a.status is status and a.updated_at < before
        ]

    async def list_by_status(self, *, status: MediaStatus) -> list[MediaAsset]:
        """Return all assets in `status`."""
        return [a for a in self._assets.values() if a.status is status]

    async def delete(self, asset_id: uuid.UUID) -> None:
        """Hard-delete the asset record."""
        self._assets.pop(asset_id, None)
