import uuid

import pytest

from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.application.update_media import UpdateMedia, UpdateMediaCommand
from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_use_case() -> tuple[UpdateMedia, InMemoryMediaAssetRepository]:
    repo = InMemoryMediaAssetRepository()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    return UpdateMedia(uow), repo


async def test_update_renames_and_persists_asset() -> None:
    """UpdateMedia renames the asset and saves it via the repository."""
    use_case, repo = _make_use_case()
    asset = MediaAsset.create(
        filename="cover.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    await repo.add(asset)

    result = await use_case.handle(
        UpdateMediaCommand(asset_id=asset.id, filename="front page"), SYSTEM_ACTOR
    )

    assert result.filename == "front page.jpg"
    stored = await repo.get(asset.id)
    assert stored is not None
    assert stored.filename == "front page.jpg"


async def test_update_raises_for_missing_asset() -> None:
    """UpdateMedia raises MediaAssetNotFoundError for an unknown id."""
    use_case, _ = _make_use_case()

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(
            UpdateMediaCommand(asset_id=uuid.uuid4(), filename="new-name"),
            SYSTEM_ACTOR,
        )
