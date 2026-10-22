from typing import TYPE_CHECKING

import pytest

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
from app.modules.media.application.stage_media import StageMedia, StageMediaCommand
from app.modules.media.domain.errors import ImageTooLargeError, MediaFileTooLargeError
from app.modules.media.domain.media_asset import MediaStatus
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _stream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def _make_use_case(
    image_processor: InMemoryImageProcessor | None = None,
) -> tuple[StageMedia, InMemoryMediaAssetRepository, InMemoryMediaStorage]:
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=repo))
    proc = image_processor or InMemoryImageProcessor()
    return StageMedia(uow, InMemoryAccessGuard(), storage, proc), repo, storage


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
    assert await repo.get(asset.id, scope=ContentFilter.everyone()) is asset
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


async def test_stage_generates_thumbnail_for_image() -> None:
    """StageMedia generates and stores a thumbnail when content is thumbnailable."""
    use_case, _repo, storage = _make_use_case()

    asset = await use_case.handle(
        StageMediaCommand(
            filename="photo.jpg",
            content_type="image/jpeg",
            sniffed_content_type="image/jpeg",
            stream=_stream(b"real-image-bytes"),
        ),
        SYSTEM_ACTOR,
    )

    assert asset.has_thumbnail is True
    assert (asset.id, "staged") in storage._thumbnails


async def test_stage_skips_thumbnail_when_processor_returns_none() -> None:
    """StageMedia skips thumbnailing gracefully when processor returns None."""
    proc = InMemoryImageProcessor(generate_result=False)
    use_case, _repo, storage = _make_use_case(image_processor=proc)

    asset = await use_case.handle(
        StageMediaCommand(
            filename="photo.jpg",
            content_type="image/jpeg",
            sniffed_content_type="image/jpeg",
            stream=_stream(b"invalid-image-bytes"),
        ),
        SYSTEM_ACTOR,
    )

    assert asset.has_thumbnail is False
    assert (asset.id, "staged") not in storage._thumbnails


async def test_stage_warns_on_filename_extension_mismatch_and_downgrades() -> None:
    """StageMedia warns on extension mismatch and downgrades unconfirmed type."""
    use_case, _repo, _storage = _make_use_case()

    asset = await use_case.handle(
        StageMediaCommand(
            filename="report.pdf",
            content_type="image/jpeg",
            sniffed_content_type=None,
            stream=_stream(b"not-jpeg-bytes"),
        ),
        SYSTEM_ACTOR,
    )

    assert asset.content_type == "application/octet-stream"
    assert asset.has_thumbnail is False


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


async def test_stage_logs_a_sanitised_filename() -> None:
    """A client filename with escape codes or great length is neutralised in logs."""
    from structlog.testing import capture_logs

    use_case, _, _ = _make_use_case()
    hostile = "\x1b[2Jevil\r\n" + "a" * 500 + ".jpg"

    with capture_logs() as logs:
        await use_case.handle(
            StageMediaCommand(
                filename=hostile, content_type="image/jpeg", stream=_stream(b"x")
            ),
            SYSTEM_ACTOR,
        )

    (entry,) = [e for e in logs if e["event"] == "media staged"]
    assert "\x1b" not in entry["filename"]
    assert "\r" not in entry["filename"]
    assert entry["filename"].startswith("\\x1b[2Jevil\\x0d\\x0a")
    assert len(entry["filename"]) <= 103


async def test_stage_refuses_an_image_too_large_to_decode_and_cleans_up() -> None:
    """A decompression bomb is a validation error; nothing stays staged."""
    use_case, repo, storage = _make_use_case(InMemoryImageProcessor(too_large=True))

    with pytest.raises(ImageTooLargeError):
        await use_case.handle(
            StageMediaCommand(
                filename="bomb.png",
                content_type="image/png",
                sniffed_content_type="image/png",
                stream=_stream(b"data"),
            ),
            SYSTEM_ACTOR,
        )

    assert storage._files == {}
    assert (
        await repo.list_by_status(
            status=MediaStatus.STAGED, scope=ContentFilter.everyone()
        )
        == []
    )
