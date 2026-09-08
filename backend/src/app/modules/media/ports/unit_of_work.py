from dataclasses import dataclass

from app.modules.media.ports.media_asset_repository import MediaAssetRepository
from app.modules.media.ports.media_attachment_repository import (
    MediaAttachmentRepository,
)
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class MediaRepos:
    """The media module's repository bundle."""

    assets: MediaAssetRepository
    attachments: MediaAttachmentRepository


MediaUnitOfWork = UnitOfWork[MediaRepos]
