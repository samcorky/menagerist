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
from app.modules.media.application.delete_media import DeleteMedia, DeleteMediaCommand
from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_use_case() -> tuple[
    DeleteMedia, InMemoryMediaAssetRepository, InMemoryMediaStorage
]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    return DeleteMedia(uow, storage), repo, storage


async def test_delete_removes_asset_from_db_and_storage() -> None:
    """DeleteMedia hard-deletes the DB record and the stored file."""
    use_case, repo, storage = _make_use_case()
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    await repo.add(asset)
    storage._files[(asset.id, "staged")] = b"data"

    await use_case.handle(DeleteMediaCommand(asset_id=asset.id), SYSTEM_ACTOR)

    assert await repo.get(asset.id) is None
    assert (asset.id, "staged") not in storage._files


async def test_delete_raises_for_missing_asset() -> None:
    """DeleteMedia raises MediaAssetNotFoundError for an unknown id."""
    use_case, _, _ = _make_use_case()

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(DeleteMediaCommand(asset_id=uuid.uuid4()), SYSTEM_ACTOR)
