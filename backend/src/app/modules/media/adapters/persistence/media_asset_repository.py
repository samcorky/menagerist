from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from app.modules.media.adapters.persistence.models import MediaAssetModel
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: MediaAssetModel) -> MediaAsset:
    """Convert an ORM row into the domain entity."""
    return MediaAsset(
        id=model.id,
        filename=model.filename,
        content_type=model.content_type,
        size=model.size,
        sha256=model.sha256,
        status=MediaStatus(model.status),
        has_thumbnail=model.has_thumbnail,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_model(asset: MediaAsset) -> MediaAssetModel:
    """Convert a domain entity into its ORM row."""
    return MediaAssetModel(
        id=asset.id,
        filename=asset.filename,
        content_type=asset.content_type,
        size=asset.size,
        sha256=asset.sha256,
        status=asset.status.value,
        has_thumbnail=asset.has_thumbnail,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


class SqlAlchemyMediaAssetRepository:
    """Postgres-backed `MediaAssetRepository`, scoped to a single session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, asset: MediaAsset) -> None:
        """Persist a new media asset."""
        self._session.add(_to_model(asset))
        await self._session.flush()

    async def save(self, asset: MediaAsset) -> None:
        """Persist changes to an existing media asset."""
        await self._session.merge(_to_model(asset))
        await self._session.flush()

    async def get(self, asset_id: uuid.UUID) -> MediaAsset | None:
        """Return the asset with `asset_id`, or `None` if it does not exist."""
        model = await self._session.get(MediaAssetModel, asset_id)
        if model is None:
            return None
        return _to_domain(model)

    async def list_expired(
        self,
        *,
        status: MediaStatus,
        before: datetime,
    ) -> list[MediaAsset]:
        """Return assets in `status` whose `updated_at` is before `before`."""
        stmt = select(MediaAssetModel).where(
            MediaAssetModel.status == status.value,
            MediaAssetModel.updated_at < before,
        )
        result = await self._session.execute(stmt)
        return [_to_domain(m) for m in result.scalars()]

    async def list_by_status(self, *, status: MediaStatus) -> list[MediaAsset]:
        """Return all assets in `status`."""
        stmt = select(MediaAssetModel).where(MediaAssetModel.status == status.value)
        result = await self._session.execute(stmt)
        return [_to_domain(m) for m in result.scalars()]

    async def delete(self, asset_id: uuid.UUID) -> None:
        """Hard-delete the asset record."""
        await self._session.execute(
            delete(MediaAssetModel).where(MediaAssetModel.id == asset_id)
        )
        await self._session.flush()
