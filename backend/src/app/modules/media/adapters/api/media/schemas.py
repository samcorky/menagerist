import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.media.application.attach_media import AttachMediaCommand
from app.modules.media.application.clear_media_cover import ClearMediaCoverCommand
from app.modules.media.application.detach_media import DetachMediaCommand
from app.modules.media.application.set_media_cover import SetMediaCoverCommand
from app.modules.media.application.update_media import UpdateMediaCommand
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.media_attachment import AttachmentKey, AttachmentTarget
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.media.application.list_node_media import NodeMediaItem
    from app.modules.media.domain.media_asset import MediaAsset
    from app.modules.media.domain.media_attachment import MediaAttachment

_ATTACHMENT_EXAMPLE: dict[str, Any] = {
    "target_type": "node",
    "target_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
    "attribute_key": "cover",
}


class AttachMediaRequest(RequestModel):
    """Request body for attaching an already-staged asset to a graph entity."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ATTACHMENT_EXAMPLE]})

    target_type: AttachmentTarget
    target_id: uuid.UUID = Field(description="The id of what to attach it to.")
    attribute_key: AttachmentKey | None = Field(
        default=None,
        description="The slot it fills, such as `cover`; none for a plain attachment.",
    )

    def to_command(self, asset_id: uuid.UUID) -> AttachMediaCommand:
        """Convert this request into an `AttachMediaCommand` for `asset_id`."""
        return AttachMediaCommand(
            asset_id=asset_id,
            target_type=self.target_type,
            target_id=self.target_id,
            attribute_key=self.attribute_key,
        )


class DetachMediaRequest(RequestModel):
    """Query parameters identifying the attachment to remove for a given asset."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ATTACHMENT_EXAMPLE]})

    target_type: AttachmentTarget = Field(description="What the asset is attached to.")
    target_id: uuid.UUID = Field(description="The id of what it is attached to.")
    attribute_key: AttachmentKey | None = Field(
        default=None,
        description="The slot it fills, such as `cover`; none for a plain attachment.",
    )

    def to_command(self, asset_id: uuid.UUID) -> DetachMediaCommand:
        """Convert this request into a `DetachMediaCommand` for `asset_id`."""
        return DetachMediaCommand(
            asset_id=asset_id,
            target_type=self.target_type,
            target_id=self.target_id,
            attribute_key=self.attribute_key,
        )


class CoverRequest(RequestModel):
    """The target whose cover to set (a body) or clear (query parameters)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "target_type": "node",
                    "target_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
                }
            ]
        }
    )

    target_type: AttachmentTarget = Field(description="What the asset is attached to.")
    target_id: uuid.UUID = Field(description="The id of what it is attached to.")

    def to_set_command(self, asset_id: uuid.UUID) -> SetMediaCoverCommand:
        """Convert this request into a `SetMediaCoverCommand` for `asset_id`."""
        return SetMediaCoverCommand(
            asset_id=asset_id,
            target_type=self.target_type,
            target_id=self.target_id,
        )

    def to_clear_command(self, asset_id: uuid.UUID) -> ClearMediaCoverCommand:
        """Convert this request into a `ClearMediaCoverCommand` for `asset_id`."""
        return ClearMediaCoverCommand(
            asset_id=asset_id,
            target_type=self.target_type,
            target_id=self.target_id,
        )


class UpdateMediaRequest(RequestModel):
    """Request body for updating a media asset."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"filename": "front page"}]}
    )

    filename: str = Field(description="The new file name.")

    def to_command(self, asset_id: uuid.UUID) -> UpdateMediaCommand:
        """Convert this request into an `UpdateMediaCommand` for `asset_id`."""
        return UpdateMediaCommand(asset_id=asset_id, filename=self.filename)


_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20",
    "filename": "cover.jpg",
    "content_type": "image/jpeg",
    "size": 2_048_00,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "status": "attached",
    "content_url": "/api/v1/media/01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20/content",
    "thumbnail_url": "/api/v1/media/01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20/thumbnail",
    "created_at": "2026-09-07T10:00:00Z",
    "updated_at": "2026-09-07T10:00:00Z",
}


class MediaAssetResponse(BaseModel):
    """A media asset as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE]})

    id: uuid.UUID = Field(description="The asset's id.")
    filename: str = Field(description="Its file name.")
    content_type: str = Field(description="Its media type, such as `image/jpeg`.")
    size: int = Field(description="Its size in bytes.")
    sha256: str = Field(description="The SHA-256 of its bytes, in hex.")
    status: MediaStatus
    content_url: str = Field(description="Where to download the file.")
    thumbnail_url: str | None = Field(
        description="Where to fetch a WebP thumbnail; null if there is none."
    )
    created_at: datetime = Field(description="When it was uploaded.")
    updated_at: datetime = Field(description="When it last changed.")

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
            thumbnail_url=(
                f"/api/v1/media/{asset.id}/thumbnail" if asset.has_thumbnail else None
            ),
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )


class NodeMediaItemResponse(BaseModel):
    """A media asset with its attachment slot label, as returned by list_node_media."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{**_EXAMPLE, "attribute_key": "cover"}],
        }
    )

    id: uuid.UUID = Field(description="The asset's id.")
    filename: str = Field(description="Its file name.")
    content_type: str = Field(description="Its media type, such as `image/jpeg`.")
    size: int = Field(description="Its size in bytes.")
    sha256: str = Field(description="The SHA-256 of its bytes, in hex.")
    status: MediaStatus
    content_url: str = Field(description="Where to download the file.")
    thumbnail_url: str | None = Field(
        description="Where to fetch a WebP thumbnail; null if there is none."
    )
    created_at: datetime = Field(description="When it was uploaded.")
    updated_at: datetime = Field(description="When it last changed.")
    attribute_key: AttachmentKey | None = Field(
        description="The slot it fills on the item, such as `cover`; null if none."
    )

    @classmethod
    def from_domain(cls, item: NodeMediaItem) -> NodeMediaItemResponse:
        """Build a response from a `NodeMediaItem`."""
        base = MediaAssetResponse.from_domain(item.asset)
        return cls(**base.model_dump(), attribute_key=item.attribute_key)


class MediaAttachmentResponse(BaseModel):
    """A media attachment record as returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e21",
                    "asset_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20",
                    "target_type": "node",
                    "target_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
                    "attribute_key": "cover",
                    "created_at": "2026-09-07T10:00:00Z",
                }
            ]
        }
    )

    id: uuid.UUID = Field(description="The attachment's id.")
    asset_id: uuid.UUID = Field(description="The asset attached.")
    target_type: str = Field(description="What it is attached to: `node` or `edge`.")
    target_id: uuid.UUID = Field(description="The id of what it is attached to.")
    attribute_key: AttachmentKey | None = Field(
        description="The slot it fills, such as `cover`; null for a plain attachment."
    )
    created_at: datetime = Field(description="When it was attached.")

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
