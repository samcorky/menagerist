import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
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
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.shared_kernel.access_guard import AccessGuard, InMemoryAccessGuard
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ForbiddenError, ValidationError


def _make_use_case(
    *, guard: AccessGuard | None = None
) -> tuple[CleanupExpiredMedia, InMemoryMediaAssetRepository, InMemoryMediaStorage]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    use_case = CleanupExpiredMedia(uow, guard or InMemoryAccessGuard(), storage)
    return use_case, repo, storage


def _command(
    *, staged_hours: int = 24, orphaned_hours: int = 72, batch_size: int = 100
) -> CleanupExpiredMediaCommand:
    now = datetime.now(UTC)
    return CleanupExpiredMediaCommand(
        staged_before=now - timedelta(hours=staged_hours),
        orphaned_before=now - timedelta(hours=orphaned_hours),
        batch_size=batch_size,
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


async def test_cleanup_is_refused_to_anyone_but_the_system_actor() -> None:
    """The job is system-only: a member cannot sweep, and nothing is deleted."""
    use_case, repo, storage = _make_use_case(guard=get_access_guard())
    expired = await _add_expired_staged(repo, storage)
    member = Actor(id=uuid.uuid7(), roles=frozenset({"member"}))

    for actor in (member, ANONYMOUS_ACTOR):
        with pytest.raises(ForbiddenError):
            await use_case.handle(_command(), actor)

    assert await repo.get(expired.id, scope=ContentFilter.everyone()) is expired


class _UnpluggedStorage(InMemoryMediaStorage):
    """Storage whose deletes always fail."""

    async def delete(self, asset_id: uuid.UUID, status: MediaStatus) -> None:
        raise OSError("disk unplugged")


class _CountingUnitOfWork:
    """Wrap a unit of work to count commits."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.commits = 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    async def __aenter__(self) -> object:
        return await self._inner.__aenter__()  # type: ignore[attr-defined]

    async def __aexit__(self, *exc: object) -> None:
        await self._inner.__aexit__(*exc)  # type: ignore[attr-defined]

    async def commit(self) -> None:
        self.commits += 1
        await self._inner.commit()  # type: ignore[attr-defined]


async def test_cleanup_works_through_a_backlog_in_batches() -> None:
    """Five expired assets with a batch of two take three commits, not five."""
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = _CountingUnitOfWork(
        create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    )
    use_case = CleanupExpiredMedia(uow, InMemoryAccessGuard(), storage)  # type: ignore[arg-type]
    assets = [await _add_expired_staged(repo, storage) for _ in range(5)]

    count = await use_case.handle(_command(batch_size=2), SYSTEM_ACTOR)

    assert count == 5
    assert uow.commits == 3
    for asset in assets:
        assert await repo.get(asset.id, scope=ContentFilter.everyone()) is None
        assert (asset.id, "staged") not in storage._files


async def test_files_go_only_after_their_rows_are_committed() -> None:
    """A failing file delete leaves a stray file, never a row pointing at nothing."""
    repo = InMemoryMediaAssetRepository()
    storage = _UnpluggedStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    use_case = CleanupExpiredMedia(uow, InMemoryAccessGuard(), storage)
    expired = await _add_expired_staged(repo, storage)

    with pytest.raises(OSError, match="disk unplugged"):
        await use_case.handle(_command(), SYSTEM_ACTOR)

    assert await repo.get(expired.id, scope=ContentFilter.everyone()) is None


@pytest.mark.parametrize("size", [0, -1])
def test_the_batch_size_must_be_positive(size: int) -> None:
    """A zero batch would loop forever."""
    with pytest.raises(ValidationError):
        CleanupExpiredMediaCommand(
            staged_before=datetime.now(UTC),
            orphaned_before=datetime.now(UTC),
            batch_size=size,
        )
