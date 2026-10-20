"""Bridge instance backups to original media records and storage."""

from typing import TYPE_CHECKING

from app.modules.backup.domain.backup import MediaFileRef
from app.modules.backup.domain.errors import MediaFileMissingError
from app.modules.media.domain.media_asset import MediaStatus
from app.shared_kernel.access_scope import AccessScope

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.media.ports.media_asset_repository import MediaAssetRepository
    from app.modules.media.ports.media_storage import MediaStoragePort


class BackupMediaFiles:
    """Read originals across owners and preserve their lifecycle buckets."""

    def __init__(
        self,
        repository: MediaAssetRepository,
        storage: MediaStoragePort,
        *,
        scope: AccessScope | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        # Instance backups deliberately include every owner's originals.
        self._scope = scope if scope is not None else AccessScope.everyone()

    async def list_files(self) -> list[MediaFileRef]:
        """List original assets in all lifecycle buckets, across the instance."""
        refs: list[MediaFileRef] = []
        for status in MediaStatus:
            assets = await self._repository.list_by_status(
                status=status, scope=self._scope
            )
            refs.extend(
                MediaFileRef(
                    asset_id=asset.id,
                    status=asset.status.value,
                    size=asset.size,
                    sha256=asset.sha256,
                )
                for asset in assets
            )
        return refs

    async def open(self, ref: MediaFileRef) -> AsyncIterator[bytes]:
        """Stream an original, translating a missing storage file."""
        try:
            async for chunk in self._storage.retrieve(
                ref.asset_id, MediaStatus(ref.status)
            ):
                yield chunk
        except FileNotFoundError as exc:
            raise MediaFileMissingError(
                f"Missing media original {ref.asset_id}"
            ) from exc

    async def write(self, ref: MediaFileRef, stream: AsyncIterator[bytes]) -> None:
        """Write an original into the archived lifecycle bucket."""
        await self._storage.store(ref.asset_id, MediaStatus(ref.status), stream)

    async def remove(self, ref: MediaFileRef) -> None:
        """Remove an original written by an unsuccessful restore."""
        await self._storage.delete(ref.asset_id, MediaStatus(ref.status))
