from typing import TYPE_CHECKING

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
from app.modules.media.application.stage_media import StageMedia, StageMediaCommand
from app.modules.media.domain.errors import MediaFileTooLargeError
from app.modules.media.domain.media_asset import MediaStatus
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _stream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def _make_use_case() -> tuple[
    StageMedia, InMemoryMediaAssetRepository, InMemoryMediaStorage
]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    return StageMedia(uow, storage), repo, storage


async def test_stage_persists_asset_and_commits() -> None:
    """StageMedia stores the file and commits the DB record."""
    use_case, repo, storage = _make_use_case()

    asset = await use_case.handle(
        StageMediaCommand(
            filename="cover.jpg",
            content_type="image/jpeg",
            stream=_stream(b"hello"),
        ),
        SYSTEM_ACTOR,
    )

    assert asset.status is MediaStatus.STAGED
    assert asset.filename == "cover.jpg"
    assert asset.size == 5
    assert await repo.get(asset.id) is asset
    assert storage._files[(asset.id, "staged")] == b"hello"


async def test_stage_computes_sha256() -> None:
    """StageMedia records the sha256 of the uploaded bytes."""
    import hashlib

    use_case, _, _ = _make_use_case()
    data = b"hello world"

    asset = await use_case.handle(
        StageMediaCommand(
            filename="f.txt",
            content_type="text/plain",
            stream=_stream(data),
        ),
        SYSTEM_ACTOR,
    )

    assert asset.sha256 == hashlib.sha256(data).hexdigest()


async def test_stage_raises_when_file_too_large() -> None:
    """StageMedia raises MediaFileTooLargeError when max_size is exceeded."""
    use_case, _, _ = _make_use_case()

    import pytest

    with pytest.raises(MediaFileTooLargeError):
        await use_case.handle(
            StageMediaCommand(
                filename="big.bin",
                content_type="application/octet-stream",
                stream=_stream(b"x" * 100),
                max_size=10,
            ),
            SYSTEM_ACTOR,
        )
