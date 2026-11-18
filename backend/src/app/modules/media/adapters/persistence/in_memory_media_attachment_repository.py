from typing import TYPE_CHECKING

from app.modules.media.domain.errors import CoverAlreadySetError
from app.modules.media.domain.media_attachment import AttachmentKey

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection

    from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (  # noqa: E501
        InMemoryMediaAssetRepository,
    )
    from app.modules.media.domain.media_asset import MediaAsset
    from app.modules.media.domain.media_attachment import (
        AttachmentTarget,
        MediaAttachment,
    )
    from app.shared_kernel.content_filter import ContentFilter


class InMemoryMediaAttachmentRepository:
    """Dict-backed `MediaAttachmentRepository` for tests - no database required.

    Reads the asset twin's owners to apply a scope, as the SQL twin joins them.
    """

    def __init__(self, assets: InMemoryMediaAssetRepository) -> None:
        self._assets = assets
        self._store: dict[uuid.UUID, MediaAttachment] = {}

    def _visible(self, attachment: MediaAttachment, scope: ContentFilter) -> bool:
        """Whether the attachment's asset is inside `scope`."""
        return scope.covers(self._assets.owner_of(attachment.asset_id))

    async def lock_target(
        self, target_type: AttachmentTarget, target_id: uuid.UUID
    ) -> None:
        """Do nothing: in-memory calls never interleave inside a use case."""

    async def add(self, attachment: MediaAttachment) -> None:
        """Store an attachment.

        Raises:
            CoverAlreadySetError: If it is a second cover for its target.
        """
        if attachment.attribute_key is AttachmentKey.COVER and any(
            a.attribute_key is AttachmentKey.COVER
            and a.target_type == attachment.target_type
            and a.target_id == attachment.target_id
            for a in self._store.values()
        ):
            raise CoverAlreadySetError
        self._store[attachment.id] = attachment

    async def get(
        self, attachment_id: uuid.UUID, *, scope: ContentFilter
    ) -> MediaAttachment | None:
        """Return an attachment by id, or ``None`` if missing or unseen."""
        found = self._store.get(attachment_id)
        return found if found is not None and self._visible(found, scope) else None

    async def list_cover_assets(
        self,
        target_type: AttachmentTarget,
        target_ids: Collection[uuid.UUID],
        *,
        scope: ContentFilter,
    ) -> dict[uuid.UUID, MediaAsset]:
        """Return the cover asset of each target that has one inside `scope`."""
        covers: dict[uuid.UUID, MediaAsset] = {}
        for attachment in self._store.values():
            if (
                attachment.attribute_key is AttachmentKey.COVER
                and attachment.target_type == target_type
                and attachment.target_id in target_ids
                and self._visible(attachment, scope)
            ):
                asset = self._assets.peek(attachment.asset_id)
                if asset is not None:
                    covers[attachment.target_id] = asset
        return covers

    async def list_for_target(
        self,
        target_type: AttachmentTarget,
        target_id: uuid.UUID,
        *,
        scope: ContentFilter,
    ) -> list[MediaAttachment]:
        """Return the attachments on the target whose asset is inside `scope`."""
        return [
            a
            for a in self._store.values()
            if a.target_type == target_type
            and a.target_id == target_id
            and self._visible(a, scope)
        ]

    async def list_for_asset(
        self, asset_id: uuid.UUID, *, scope: ContentFilter
    ) -> list[MediaAttachment]:
        """Return the attachments of the asset, if the asset is inside `scope`."""
        return [
            a
            for a in self._store.values()
            if a.asset_id == asset_id and self._visible(a, scope)
        ]

    async def update(self, attachment: MediaAttachment) -> None:
        """Persist changes to an existing attachment (no-op if absent)."""
        if attachment.id in self._store:
            self._store[attachment.id] = attachment

    async def delete(self, attachment_id: uuid.UUID) -> None:
        """Remove an attachment by id (no-op if absent)."""
        self._store.pop(attachment_id, None)
