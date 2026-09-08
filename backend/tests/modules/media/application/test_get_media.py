import uuid

import pytest

from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.application.get_media import GetMedia, GetMediaQuery
from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_use_case() -> tuple[GetMedia, InMemoryMediaAssetRepository]:
    repo = InMemoryMediaAssetRepository()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    return GetMedia(uow), repo


async def test_get_returns_asset_by_id() -> None:
    """GetMedia returns the asset for a known id."""
    use_case, repo = _make_use_case()
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    await repo.add(asset)

    result = await use_case.handle(GetMediaQuery(asset_id=asset.id), SYSTEM_ACTOR)

    assert result is asset


async def test_get_raises_for_missing_id() -> None:
    """GetMedia raises MediaAssetNotFoundError for an unknown id."""
    use_case, _ = _make_use_case()

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(GetMediaQuery(asset_id=uuid.uuid4()), SYSTEM_ACTOR)
