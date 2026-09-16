import uuid
from datetime import UTC, datetime, timedelta

from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus


def _make_asset(**kwargs: object) -> MediaAsset:
    defaults: dict[str, object] = {
        "filename": "f.jpg",
        "content_type": "image/jpeg",
        "size": 1,
        "sha256": "abc",
    }
    defaults.update(kwargs)
    return MediaAsset.create(**defaults)  # type: ignore[arg-type]


async def test_add_and_get_round_trips() -> None:
    """An asset added to the repository can be retrieved by id."""
    repo = InMemoryMediaAssetRepository()
    asset = _make_asset()

    await repo.add(asset)

    assert await repo.get(asset.id) is asset


async def test_get_returns_none_for_missing_id() -> None:
    """get() returns None for an id that was never added."""
    repo = InMemoryMediaAssetRepository()

    assert await repo.get(uuid.uuid4()) is None


async def test_save_overwrites_existing_record() -> None:
    """save() replaces the stored instance so reads see the updated object."""
    repo = InMemoryMediaAssetRepository()
    asset = _make_asset()
    await repo.add(asset)

    asset.promote()
    await repo.save(asset)

    result = await repo.get(asset.id)
    assert result is not None
    assert result.status is MediaStatus.ATTACHED


async def test_delete_removes_the_record() -> None:
    """delete() hard-removes the record so get() returns None afterwards."""
    repo = InMemoryMediaAssetRepository()
    asset = _make_asset()
    await repo.add(asset)

    await repo.delete(asset.id)

    assert await repo.get(asset.id) is None


async def test_delete_is_idempotent() -> None:
    """delete() on a missing id does not raise."""
    repo = InMemoryMediaAssetRepository()

    await repo.delete(uuid.uuid4())  # should not raise


async def test_list_expired_returns_assets_with_matching_status_before_cutoff() -> None:
    """list_expired() filters by status and updated_at < before."""
    repo = InMemoryMediaAssetRepository()
    old_asset = _make_asset()
    old_asset.updated_at = datetime.now(UTC) - timedelta(hours=25)
    await repo.add(old_asset)

    fresh_asset = _make_asset()
    await repo.add(fresh_asset)

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    result = await repo.list_expired(status=MediaStatus.STAGED, before=cutoff)

    assert old_asset in result
    assert fresh_asset not in result


async def test_list_by_status_returns_only_matching_assets() -> None:
    """list_by_status() returns assets whose status matches, and no others."""
    repo = InMemoryMediaAssetRepository()
    staged = _make_asset()
    await repo.add(staged)

    attached = _make_asset()
    attached.promote()
    await repo.add(attached)

    result = await repo.list_by_status(status=MediaStatus.ATTACHED)

    assert attached in result
    assert staged not in result


async def test_list_expired_filters_by_status() -> None:
    """list_expired() only returns assets whose status matches."""
    repo = InMemoryMediaAssetRepository()
    staged = _make_asset()
    staged.updated_at = datetime.now(UTC) - timedelta(hours=48)
    await repo.add(staged)

    attached = _make_asset()
    attached.promote()
    attached.updated_at = datetime.now(UTC) - timedelta(hours=48)
    await repo.add(attached)

    cutoff = datetime.now(UTC)
    result = await repo.list_expired(status=MediaStatus.STAGED, before=cutoff)

    assert staged in result
    assert attached not in result
