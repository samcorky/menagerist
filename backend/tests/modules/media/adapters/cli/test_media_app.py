import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from app.modules.media.adapters.cli.media_app import cleanup, regenerate_thumbnails
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
from app.modules.media.domain.media_asset import MediaAsset
from app.platform.config.media import MediaSettings


def test_cleanup_wires_the_use_case_and_deletes_expired_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `media cleanup` command wires real deps and deletes expired assets."""
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    settings = MediaSettings(staged_ttl_hours=24, orphaned_ttl_hours=72)

    expired = MediaAsset.create(
        filename="old.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    expired.updated_at = datetime.now(UTC) - timedelta(hours=48)
    asyncio.run(repo.add(expired))
    storage._files[(expired.id, "staged")] = b"data"

    monkeypatch.setattr(
        "app.modules.media.adapters.persistence.unit_of_work.create_media_uow",
        lambda _factory: uow,
    )
    monkeypatch.setattr(
        "app.modules.media.adapters.storage.local_filesystem.LocalFilesystemMediaStorage",
        lambda _path: storage,
    )
    monkeypatch.setattr(
        "app.platform.config.media.get_media_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.platform.database.get_session_factory",
        lambda: object(),
    )

    cleanup()

    assert asyncio.run(repo.get(expired.id)) is None


def test_regenerate_thumbnails_wires_the_use_case_and_regenerates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `media regenerate-thumbnails` command wires real deps and regenerates."""
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    processor = InMemoryImageProcessor()

    asset = MediaAsset.create(
        filename="cover.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    asyncio.run(repo.add(asset))
    storage._files[(asset.id, "attached")] = b"original-bytes"

    monkeypatch.setattr(
        "app.modules.media.adapters.persistence.unit_of_work.create_media_uow",
        lambda _factory: uow,
    )
    monkeypatch.setattr(
        "app.modules.media.adapters.storage.local_filesystem.LocalFilesystemMediaStorage",
        lambda _path: storage,
    )
    monkeypatch.setattr(
        "app.modules.media.adapters.imaging.pillow_processor.PillowImageProcessor",
        lambda: processor,
    )
    monkeypatch.setattr(
        "app.platform.config.media.get_media_settings",
        lambda: MediaSettings(),
    )
    monkeypatch.setattr(
        "app.platform.database.get_session_factory",
        lambda: object(),
    )

    regenerate_thumbnails()

    assert storage._thumbnails[(asset.id, "attached")] == b"fake-webp-thumbnail"
