from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
    from app.shared_kernel.access_scope import AccessScope


class MediaAssetRepository(Protocol):
    """Access to media asset records, independent of storage backend."""

    async def add(self, asset: MediaAsset) -> None:
        """Persist a new media asset."""
        ...

    async def save(self, asset: MediaAsset) -> None:
        """Persist changes to an existing media asset."""
        ...

    async def get(
        self, asset_id: uuid.UUID, *, scope: AccessScope
    ) -> MediaAsset | None:
        """Return the asset with `asset_id`, or `None` if missing or unseen."""
        ...

    async def list_expired(
        self,
        *,
        status: MediaStatus,
        before: datetime,
        scope: AccessScope,
    ) -> list[MediaAsset]:
        """Return assets in `scope` and `status` last updated before `before`."""
        ...

    async def list_by_status(
        self, *, status: MediaStatus, scope: AccessScope
    ) -> list[MediaAsset]:
        """Return all assets in `scope` that are in `status`."""
        ...

    async def delete(self, asset_id: uuid.UUID) -> None:
        """Hard-delete the asset record."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every asset with no owner or a legacy owner.

        System-level and unscoped, deleted rows included. Returns the count.
        """
        ...
