import uuid
from datetime import UTC, datetime, timedelta

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
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
from app.modules.media.application.cleanup_expired_media import (
    CleanupExpiredMedia,
    CleanupExpiredMediaCommand,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter


def _make_use_case() -> tuple[
    CleanupExpiredMedia, InMemoryMediaAssetRepository, InMemoryMediaStorage
]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    return CleanupExpiredMedia(uow, OwnerAccessPolicy(), storage), repo, storage


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
        owner_id=SYSTEM_ACTOR.id,
        filename="old.jpg",
        content_type="image/jpeg",
        size=1,
        sha256="x",
    )
    asset.updated_at = datetime.now(UTC) - timedelta(hours=48)
    await repo.add(asset)
    storage._files[(asset.id, "staged")] = b"data"
    return asset


async def _add_expired_orphaned(
    repo: InMemoryMediaAssetRepository, storage: InMemoryMediaStorage
) -> MediaAsset:
    asset = MediaAsset.create(
        owner_id=SYSTEM_ACTOR.id,
        filename="old.jpg",
        content_type="image/jpeg",
        size=1,
        sha256="x",
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
    assert await repo.get(expired.id, scope=ContentFilter.everyone()) is None
    assert (expired.id, "staged") not in storage._files


async def test_cleanup_deletes_expired_orphaned_assets() -> None:
    """CleanupExpiredMedia removes orphaned assets past their TTL."""
    use_case, repo, storage = _make_use_case()
    expired = await _add_expired_orphaned(repo, storage)

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 1
    assert await repo.get(expired.id, scope=ContentFilter.everyone()) is None
    assert (expired.id, "orphaned") not in storage._files


async def test_cleanup_leaves_fresh_assets_untouched() -> None:
    """CleanupExpiredMedia does not touch assets within their TTL."""
    use_case, repo, storage = _make_use_case()
    fresh = MediaAsset.create(
        owner_id=SYSTEM_ACTOR.id,
        filename="new.jpg",
        content_type="image/jpeg",
        size=1,
        sha256="x",
    )
    await repo.add(fresh)
    storage._files[(fresh.id, "staged")] = b"data"

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 0
    assert await repo.get(fresh.id, scope=ContentFilter.everyone()) is fresh


async def test_cleanup_returns_total_deleted_count() -> None:
    """CleanupExpiredMedia returns the total number of deleted assets."""
    use_case, repo, storage = _make_use_case()
    await _add_expired_staged(repo, storage)
    await _add_expired_staged(repo, storage)
    await _add_expired_orphaned(repo, storage)

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 3


async def test_cleanup_sees_every_owners_expired_assets() -> None:
    """The system job ignores ownership, including legacy rows with no owner."""
    use_case, repo, storage = _make_use_case()
    alice = await _add_expired_staged(repo, storage)
    bob = await _add_expired_orphaned(repo, storage)
    alice.owner_id = uuid.UUID(int=101)
    bob.owner_id = uuid.UUID(int=102)
    legacy = await _add_expired_staged(repo, storage)
    legacy.owner_id = None

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 3
    for asset in (alice, bob, legacy):
        assert await repo.get(asset.id, scope=ContentFilter.everyone()) is None


async def test_cleanup_follows_the_policy_scope_for_the_actor() -> None:
    """A non-system actor only cleans up its own expired assets."""
    use_case, repo, storage = _make_use_case()
    theirs = await _add_expired_staged(repo, storage)
    me = uuid.uuid7()
    theirs.owner_id = uuid.uuid7()
    mine = await _add_expired_staged(repo, storage)
    mine.owner_id = me

    count = await use_case.handle(_command(), Actor(id=me, roles=frozenset({"member"})))

    assert count == 1
    assert await repo.get(theirs.id, scope=ContentFilter.everyone()) is theirs
    assert await repo.get(mine.id, scope=ContentFilter.everyone()) is None
