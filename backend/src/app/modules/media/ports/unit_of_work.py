from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.shared_kernel.unit_of_work import UnitOfWork

if TYPE_CHECKING:
    from app.modules.media.ports.media_asset_repository import MediaAssetRepository


@dataclass(kw_only=True)
class MediaRepos:
    """The media module's repository bundle."""

    assets: "MediaAssetRepository"


MediaUnitOfWork = UnitOfWork[MediaRepos]
