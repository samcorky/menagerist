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
from app.modules.media.application.orphan_media import OrphanMedia, OrphanMediaCommand
from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import ValidationError


def _make_use_case() -> tuple[
    OrphanMedia, InMemoryMediaAssetRepository, InMemoryMediaStorage
]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    return OrphanMedia(uow, storage), repo, storage


async def _add_attached(
    repo: InMemoryMediaAssetRepository, storage: InMemoryMediaStorage
) -> MediaAsset:
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    await repo.add(asset)
    storage._files[(asset.id, "attached")] = b"data"
    return asset


async def test_orphan_transitions_asset_to_orphaned() -> None:
    """OrphanMedia transitions an attached asset to orphaned."""
    use_case, repo, storage = _make_use_case()
    asset = await _add_attached(repo, storage)

    result = await use_case.handle(OrphanMediaCommand(asset_id=asset.id), SYSTEM_ACTOR)

    assert result.status is MediaStatus.ORPHANED
    assert (await repo.get(asset.id)).status is MediaStatus.ORPHANED  # type: ignore[union-attr]
    assert storage._files.get((asset.id, "orphaned")) == b"data"
    assert (asset.id, "attached") not in storage._files


async def test_orphan_raises_for_missing_asset() -> None:
    """OrphanMedia raises MediaAssetNotFoundError for an unknown id."""
    use_case, _, _ = _make_use_case()

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(OrphanMediaCommand(asset_id=uuid.uuid4()), SYSTEM_ACTOR)


async def test_orphan_raises_if_staged() -> None:
    """OrphanMedia raises ValidationError if the asset is not attached."""
    use_case, repo, _ = _make_use_case()
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    await repo.add(asset)

    with pytest.raises(ValidationError, match="cannot orphan"):
        await use_case.handle(OrphanMediaCommand(asset_id=asset.id), SYSTEM_ACTOR)
