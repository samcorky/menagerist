from datetime import UTC, datetime, timedelta

from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.application.cleanup_expired_media import (
    CleanupExpiredMedia,
    CleanupExpiredMediaCommand,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.ports.unit_of_work import MediaRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_use_case() -> tuple[
    CleanupExpiredMedia, InMemoryMediaAssetRepository, InMemoryMediaStorage
]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(MediaRepos(assets=repo))
    return CleanupExpiredMedia(uow, storage), repo, storage


def _command(
    *, staged_hours: int = 24, orphaned_hours: int = 72
) -> CleanupExpiredMediaCommand:
    now = datetime.now(UTC)
    return CleanupExpiredMediaCommand(
        staged_before=now - timedelta(hours=staged_hours),
        orphaned_before=now - timedelta(hours=orphaned_hours),
    )


async def _add_expired_staged(
    repo: InMemoryMediaAssetRepository, storage: InMemoryMediaStorage
) -> MediaAsset:
    asset = MediaAsset.create(
        filename="old.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.updated_at = datetime.now(UTC) - timedelta(hours=48)
    await repo.add(asset)
    storage._files[(asset.id, "staged")] = b"data"
    return asset


async def _add_expired_orphaned(
    repo: InMemoryMediaAssetRepository, storage: InMemoryMediaStorage
) -> MediaAsset:
    asset = MediaAsset.create(
        filename="old.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    asset.orphan()
    asset.updated_at = datetime.now(UTC) - timedelta(hours=96)
    await repo.add(asset)
    storage._files[(asset.id, "orphaned")] = b"data"
    return asset


async def test_cleanup_deletes_expired_staged_assets() -> None:
    """CleanupExpiredMedia removes staged assets past their TTL."""
    use_case, repo, storage = _make_use_case()
    expired = await _add_expired_staged(repo, storage)

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 1
    assert await repo.get(expired.id) is None
    assert (expired.id, "staged") not in storage._files


async def test_cleanup_deletes_expired_orphaned_assets() -> None:
    """CleanupExpiredMedia removes orphaned assets past their TTL."""
    use_case, repo, storage = _make_use_case()
    expired = await _add_expired_orphaned(repo, storage)

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 1
    assert await repo.get(expired.id) is None
    assert (expired.id, "orphaned") not in storage._files


async def test_cleanup_leaves_fresh_assets_untouched() -> None:
    """CleanupExpiredMedia does not touch assets within their TTL."""
    use_case, repo, storage = _make_use_case()
    fresh = MediaAsset.create(
        filename="new.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    await repo.add(fresh)
    storage._files[(fresh.id, "staged")] = b"data"

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 0
    assert await repo.get(fresh.id) is fresh


async def test_cleanup_returns_total_deleted_count() -> None:
    """CleanupExpiredMedia returns the total number of deleted assets."""
    use_case, repo, storage = _make_use_case()
    await _add_expired_staged(repo, storage)
    await _add_expired_staged(repo, storage)
    await _add_expired_orphaned(repo, storage)

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 3
