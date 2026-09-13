from app.modules.media.adapters.imaging.in_memory_image_processor import (
    InMemoryImageProcessor,
)
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
from app.modules.media.application.regenerate_thumbnails import (
    RegenerateThumbnails,
    RegenerateThumbnailsCommand,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_use_case(
    *, image_processor: InMemoryImageProcessor | None = None
) -> tuple[RegenerateThumbnails, InMemoryMediaAssetRepository, InMemoryMediaStorage]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    processor = image_processor or InMemoryImageProcessor()
    return RegenerateThumbnails(uow, storage, processor), repo, storage


async def _add_attached(
    repo: InMemoryMediaAssetRepository,
    storage: InMemoryMediaStorage,
    *,
    content_type: str = "image/jpeg",
) -> MediaAsset:
    asset = MediaAsset.create(
        filename="cover.jpg", content_type=content_type, size=1, sha256="x"
    )
    asset.promote()
    await repo.add(asset)
    storage._files[(asset.id, "attached")] = b"original-bytes"
    return asset


async def test_regenerates_thumbnail_for_attached_image() -> None:
    """RegenerateThumbnails re-generates and re-stores an attached asset's thumbnail."""
    use_case, repo, storage = _make_use_case()
    asset = await _add_attached(repo, storage)

    count = await use_case.handle(RegenerateThumbnailsCommand(), SYSTEM_ACTOR)

    assert count == 1
    assert storage._thumbnails[(asset.id, "attached")] == b"fake-webp-thumbnail"
    updated = await repo.get(asset.id)
    assert updated is not None
    assert updated.has_thumbnail is True


async def test_skips_non_thumbnailable_content_types() -> None:
    """RegenerateThumbnails leaves non-image assets untouched."""
    use_case, repo, storage = _make_use_case()
    asset = await _add_attached(repo, storage, content_type="application/pdf")

    count = await use_case.handle(RegenerateThumbnailsCommand(), SYSTEM_ACTOR)

    assert count == 0
    assert (asset.id, "attached") not in storage._thumbnails


async def test_skips_assets_the_processor_cannot_decode() -> None:
    """RegenerateThumbnails does not count or store a thumbnail when decoding fails."""
    use_case, repo, storage = _make_use_case(
        image_processor=InMemoryImageProcessor(generate_result=False)
    )
    await _add_attached(repo, storage)

    count = await use_case.handle(RegenerateThumbnailsCommand(), SYSTEM_ACTOR)

    assert count == 0


async def test_ignores_staged_and_orphaned_assets() -> None:
    """RegenerateThumbnails only considers attached assets, not staged/orphaned ones."""
    use_case, repo, storage = _make_use_case()
    staged = MediaAsset.create(
        filename="new.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    await repo.add(staged)
    storage._files[(staged.id, "staged")] = b"original-bytes"

    count = await use_case.handle(RegenerateThumbnailsCommand(), SYSTEM_ACTOR)

    assert count == 0


async def test_skips_oversized_assets() -> None:
    """RegenerateThumbnails leaves assets above the size cap untouched."""
    use_case, repo, storage = _make_use_case()
    asset = await _add_attached(repo, storage)
    asset.size = 26 * 1024 * 1024  # above the 25 MiB cap
    await repo.save(asset)

    count = await use_case.handle(RegenerateThumbnailsCommand(), SYSTEM_ACTOR)

    assert count == 0


async def test_returns_total_regenerated_count() -> None:
    """RegenerateThumbnails returns the number of thumbnails it regenerated."""
    use_case, repo, storage = _make_use_case()
    await _add_attached(repo, storage)
    await _add_attached(repo, storage)

    count = await use_case.handle(RegenerateThumbnailsCommand(), SYSTEM_ACTOR)

    assert count == 2
