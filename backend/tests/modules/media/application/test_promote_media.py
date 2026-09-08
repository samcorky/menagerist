import uuid

import pytest

from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.application.promote_media import (
    PromoteMedia,
    PromoteMediaCommand,
)
from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import ValidationError


def _make_use_case() -> tuple[
    PromoteMedia, InMemoryMediaAssetRepository, InMemoryMediaStorage
]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    return PromoteMedia(uow, storage), repo, storage


async def _add_staged(
    repo: InMemoryMediaAssetRepository, storage: InMemoryMediaStorage
) -> MediaAsset:
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    await repo.add(asset)
    storage._files[(asset.id, "staged")] = b"data"
    return asset


async def test_promote_transitions_asset_to_attached() -> None:
    """PromoteMedia transitions a staged asset to attached."""
    use_case, repo, storage = _make_use_case()
    asset = await _add_staged(repo, storage)

    result = await use_case.handle(PromoteMediaCommand(asset_id=asset.id), SYSTEM_ACTOR)

    assert result.status is MediaStatus.ATTACHED
    assert (await repo.get(asset.id)).status is MediaStatus.ATTACHED  # type: ignore[union-attr]
    assert storage._files.get((asset.id, "attached")) == b"data"
    assert (asset.id, "staged") not in storage._files


async def test_promote_raises_for_missing_asset() -> None:
    """PromoteMedia raises MediaAssetNotFoundError for an unknown id."""
    use_case, _, _ = _make_use_case()

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(PromoteMediaCommand(asset_id=uuid.uuid4()), SYSTEM_ACTOR)


async def test_promote_raises_if_already_attached() -> None:
    """PromoteMedia raises ValidationError if the asset is not staged."""
    use_case, repo, storage = _make_use_case()
    asset = await _add_staged(repo, storage)
    await use_case.handle(PromoteMediaCommand(asset_id=asset.id), SYSTEM_ACTOR)

    with pytest.raises(ValidationError, match="cannot promote"):
        await use_case.handle(PromoteMediaCommand(asset_id=asset.id), SYSTEM_ACTOR)
