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
from app.modules.media.application.remove_stray_media_files import (
    RemoveStrayMediaFiles,
    RemoveStrayMediaFilesCommand,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError, ValidationError

type Setup = tuple[
    RemoveStrayMediaFiles, InMemoryMediaAssetRepository, InMemoryMediaStorage
]


def _setup(*, guard: object | None = None) -> Setup:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    use_case = RemoveStrayMediaFiles(
        uow,
        guard or InMemoryAccessGuard(),  # type: ignore[arg-type]
        storage,
    )
    return use_case, repo, storage


def _command(*, batch_size: int = 100) -> RemoveStrayMediaFilesCommand:
    return RemoveStrayMediaFilesCommand(
        older_than=datetime.now(UTC) - timedelta(hours=24), batch_size=batch_size
    )


def _old_file(
    storage: InMemoryMediaStorage, status: MediaStatus = MediaStatus.STAGED
) -> uuid.UUID:
    """A stored file with no database row, old enough to be considered."""
    asset_id = uuid.uuid7()
    storage._files[(asset_id, status.value)] = b"data"
    storage.modified_at[(asset_id, status.value)] = datetime.now(UTC) - timedelta(
        hours=48
    )
    return asset_id


async def _old_file_with_row(
    repo: InMemoryMediaAssetRepository, storage: InMemoryMediaStorage
) -> uuid.UUID:
    asset = MediaAsset.create(
        owner_id=SYSTEM_ACTOR.id,
        filename="kept.jpg",
        content_type="image/jpeg",
        size=1,
        sha256="x",
    )
    await repo.add(asset)
    storage._files[(asset.id, "staged")] = b"data"
    storage.modified_at[(asset.id, "staged")] = datetime.now(UTC) - timedelta(hours=48)
    return asset.id


async def test_it_removes_old_files_that_have_no_row_in_any_bucket() -> None:
    """A file whose asset is gone is deleted, with its thumbnail."""
    use_case, _, storage = _setup()
    stray = _old_file(storage)
    _old_file(storage, MediaStatus.ORPHANED)
    storage._thumbnails[(stray, "staged")] = b"t"

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 2
    assert not storage._files
    assert not storage._thumbnails


async def test_it_keeps_files_that_still_have_a_row() -> None:
    """Only files without an asset are touched, whoever owns the asset."""
    use_case, repo, storage = _setup()
    kept = await _old_file_with_row(repo, storage)
    stray = _old_file(storage)

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 1
    assert (kept, "staged") in storage._files
    assert (stray, "staged") not in storage._files


async def test_it_never_touches_a_recent_file() -> None:
    """A file newer than the cutoff may belong to an upload still in flight."""
    use_case, _, storage = _setup()
    in_flight = uuid.uuid7()
    storage._files[(in_flight, "staged")] = b"data"

    count = await use_case.handle(_command(), SYSTEM_ACTOR)

    assert count == 0
    assert (in_flight, "staged") in storage._files


async def test_it_works_through_many_files_in_batches() -> None:
    """Five strays and a kept file, in batches of two: the strays go, the file stays."""
    use_case, repo, storage = _setup()
    kept = await _old_file_with_row(repo, storage)
    for _ in range(5):
        _old_file(storage)

    count = await use_case.handle(_command(batch_size=2), SYSTEM_ACTOR)

    assert count == 5
    assert set(storage._files) == {(kept, "staged")}


async def test_it_is_refused_to_anyone_but_the_system_actor() -> None:
    """A member cannot sweep storage, and nothing is deleted."""
    use_case, _, storage = _setup(guard=get_access_guard())
    stray = _old_file(storage)
    member = Actor(id=uuid.uuid7(), roles=frozenset({"member"}))

    for actor in (member, ANONYMOUS_ACTOR):
        with pytest.raises(ForbiddenError):
            await use_case.handle(_command(), actor)

    assert (stray, "staged") in storage._files


@pytest.mark.parametrize("size", [0, -1])
def test_the_batch_size_must_be_positive(size: int) -> None:
    """A zero batch would never make progress."""
    with pytest.raises(ValidationError):
        RemoveStrayMediaFilesCommand(older_than=datetime.now(UTC), batch_size=size)


def test_the_cutoff_must_be_timezone_aware() -> None:
    """A naive cutoff would compare against the wrong clock."""
    with pytest.raises(ValidationError):
        RemoveStrayMediaFilesCommand(older_than=datetime(2026, 10, 28, 12, 0))
