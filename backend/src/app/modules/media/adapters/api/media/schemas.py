import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from app.modules.media.domain.media_asset import MediaStatus

if TYPE_CHECKING:
    from app.modules.media.domain.media_asset import MediaAsset

_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20",
    "filename": "cover.jpg",
    "content_type": "image/jpeg",
    "size": 2_048_00,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "status": "staged",
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
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )
