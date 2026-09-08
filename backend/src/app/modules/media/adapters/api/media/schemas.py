import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from app.modules.media.domain.media_asset import MediaStatus

if TYPE_CHECKING:
    from app.modules.media.domain.media_asset import MediaAsset
    from app.modules.media.domain.media_attachment import MediaAttachment

_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20",
    "filename": "cover.jpg",
    "content_type": "image/jpeg",
    "size": 2_048_00,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "status": "attached",
    "content_url": "/api/v1/media/01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20/content",
    "created_at": "2026-09-07T10:00:00Z",
    "updated_at": "2026-09-07T10:00:00Z",
}


class MediaAssetResponse(BaseModel):
    """A media asset as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE]})

    id: uuid.UUID
    filename: str
    content_type: str
    size: int
    sha256: str
    status: MediaStatus
    content_url: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, asset: MediaAsset) -> MediaAssetResponse:
        """Build a response from a domain `MediaAsset`."""
        return cls(
            id=asset.id,
            filename=asset.filename,
            content_type=asset.content_type,
            size=asset.size,
            sha256=asset.sha256,
            status=asset.status,
            content_url=f"/api/v1/media/{asset.id}/content",
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )


class MediaAttachmentResponse(BaseModel):
    """A media attachment record as returned by the API."""

    id: uuid.UUID
    asset_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    attribute_key: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, attachment: MediaAttachment) -> MediaAttachmentResponse:
        """Build a response from a domain `MediaAttachment`."""
        return cls(
            id=attachment.id,
            asset_id=attachment.asset_id,
            target_type=attachment.target_type.value,
            target_id=attachment.target_id,
            attribute_key=attachment.attribute_key,
            created_at=attachment.created_at,
        )
