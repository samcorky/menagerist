from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select

from app.modules.media.adapters.persistence.models import MediaAssetModel
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.platform.orm_mixins import claim_rows, owned_by

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


def _to_domain(model: MediaAssetModel) -> MediaAsset:
    """Convert an ORM row into the domain entity."""
    return MediaAsset(
        id=model.id,
        owner_id=model.owner_id,
        filename=model.filename,
        content_type=model.content_type,
        size=model.size,
        sha256=model.sha256,
        status=MediaStatus(model.status),
        has_thumbnail=model.has_thumbnail,
        thumbnail_sha256=model.thumbnail_sha256,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_model(asset: MediaAsset) -> MediaAssetModel:
    """Convert a domain entity into its ORM row."""
    return MediaAssetModel(
        id=asset.id,
        owner_id=asset.owner_id,
        filename=asset.filename,
        content_type=asset.content_type,
        size=asset.size,
        sha256=asset.sha256,
        status=asset.status.value,
        has_thumbnail=asset.has_thumbnail,
        thumbnail_sha256=asset.thumbnail_sha256,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _scoped(
    stmt: Select[MediaAssetModel], scope: ContentFilter
) -> Select[MediaAssetModel]:
    """Restrict a media asset select to the rows inside `scope`."""
    return stmt.where(owned_by(MediaAssetModel, scope.user_id))


class SqlAlchemyMediaAssetRepository:
    """Postgres-backed `MediaAssetRepository`, scoped to a single session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, asset: MediaAsset) -> None:
        """Persist a new media asset."""
        logger.debug("adding media asset", asset_id=asset.id)
        self._session.add(_to_model(asset))
        await self._session.flush()

    async def save(self, asset: MediaAsset) -> None:
        """Persist changes to an existing media asset."""
        logger.debug("saving media asset", asset_id=asset.id)
        await self._session.merge(_to_model(asset))
        await self._session.flush()

    async def get(
        self, asset_id: uuid.UUID, *, scope: ContentFilter
    ) -> MediaAsset | None:
        """Return the asset with `asset_id`, or `None` if missing or unseen."""
        logger.debug("fetching media asset", asset_id=asset_id)
        stmt = _scoped(
            select(MediaAssetModel).where(MediaAssetModel.id == asset_id), scope
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_expired(
        self,
        *,
        status: MediaStatus,
        before: datetime,
        scope: ContentFilter,
    ) -> list[MediaAsset]:
        """Return assets in `scope` and `status` last updated before `before`."""
        logger.debug("listing expired media assets", status=status.value)
        stmt = _scoped(
            select(MediaAssetModel).where(
                MediaAssetModel.status == status.value,
                MediaAssetModel.updated_at < before,
            ),
            scope,
        )
        result = await self._session.execute(stmt)
        return [_to_domain(m) for m in result.scalars()]

    async def list_by_status(
        self, *, status: MediaStatus, scope: ContentFilter
    ) -> list[MediaAsset]:
        """Return all assets in `scope` that are in `status`."""
        logger.debug("listing media assets by status", status=status.value)
        stmt = _scoped(
            select(MediaAssetModel).where(MediaAssetModel.status == status.value),
            scope,
        )
        result = await self._session.execute(stmt)
        return [_to_domain(m) for m in result.scalars()]

    async def delete(self, asset_id: uuid.UUID) -> None:
        """Hard-delete the asset record."""
        logger.debug("deleting media asset", asset_id=asset_id)
        await self._session.execute(
            delete(MediaAssetModel).where(MediaAssetModel.id == asset_id)
        )
        await self._session.flush()

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every asset with no owner or a legacy owner."""
        return await claim_rows(
            self._session, MediaAssetModel, owner_id, legacy_owner_ids
        )
