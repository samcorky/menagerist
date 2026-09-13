from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.media.domain.media_asset import MediaAsset, MediaStatus


class MediaAssetRepository(Protocol):
    """Access to media asset records, independent of storage backend."""

    async def add(self, asset: MediaAsset) -> None:
        """Persist a new media asset."""
        ...

    async def save(self, asset: MediaAsset) -> None:
        """Persist changes to an existing media asset."""
        ...

    async def get(self, asset_id: uuid.UUID) -> MediaAsset | None:
        """Return the asset with `asset_id`, or `None` if it does not exist."""
        ...

    async def list_expired(
        self,
        *,
        status: MediaStatus,
        before: datetime,
    ) -> list[MediaAsset]:
        """Return assets in `status` whose `updated_at` is before `before`."""
        ...

    async def list_by_status(self, *, status: MediaStatus) -> list[MediaAsset]:
        """Return all assets in `status`."""
        ...

    async def delete(self, asset_id: uuid.UUID) -> None:
        """Hard-delete the asset record."""
        ...
