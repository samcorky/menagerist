"""Tests for UploadAndAttachMedia — the composite stage+attach handler.

Key invariants:
- Both DB writes land in a single transaction (one commit).
- The storage move from STAGED→ATTACHED fires only after the DB commit.
- A sub-handler error (e.g. policy violation) rolls back the DB and
  suppresses any queued on_commit callbacks (storage move never fires).
"""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.media.adapters.imaging.in_memory_image_processor import (
    InMemoryImageProcessor,
)
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.application.upload_and_attach_media import (
    UploadAndAttachMedia,
    UploadAndAttachMediaCommand,
)
from app.modules.media.domain.errors import UnsupportedMediaTypeError
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.media_attachment import AttachmentKey, AttachmentTarget
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.media.domain.media_asset import MediaAsset
    from app.modules.media.ports.unit_of_work import MediaUnitOfWork


async def _stream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


class _AllowAllPolicy:
    async def check(self, target: AttachmentTarget, asset: MediaAsset) -> None:
        pass


class _RejectAllPolicy:
    async def check(self, target: AttachmentTarget, asset: MediaAsset) -> None:
        raise UnsupportedMediaTypeError(f"{asset.content_type!r} not permitted")


def _make_uow_and_repos() -> tuple[
    MediaUnitOfWork,
    InMemoryMediaAssetRepository,
    InMemoryMediaAttachmentRepository,
    InMemoryMediaStorage,
]:
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository()
    storage = InMemoryMediaStorage()
    repos = make_in_memory_repos(assets=assets, attachments=attachments)
    uow = create_in_memory_media_uow(repos)
    return uow, assets, attachments, storage


# ── Happy path ─────────────────────────────────────────────────────────────────


async def test_upload_and_attach_stores_file_and_persists_records() -> None:
    """Happy path: file lands in attached storage, asset+attachment rows created."""
    node_id = uuid.uuid4()
    uow, assets, _, storage = _make_uow_and_repos()
    use_case = UploadAndAttachMedia(
        uow,
        storage,
        _AllowAllPolicy(),
        InMemoryImageProcessor(),
    )

    attachment = await use_case.handle(
        UploadAndAttachMediaCommand(
            filename="photo.jpg",
            content_type="image/jpeg",
            stream=_stream(b"img-bytes"),
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert attachment.target_type is AttachmentTarget.NODE
    assert attachment.target_id == node_id

    asset = await assets.get(attachment.asset_id)
    assert asset is not None
    assert asset.status is MediaStatus.ATTACHED
    assert asset.filename == "photo.jpg"

    assert storage._files.get((asset.id, "attached")) == b"img-bytes"
    assert (asset.id, "staged") not in storage._files


async def test_upload_and_attach_single_transaction() -> None:
    """Both asset and attachment are committed in the same transaction."""
    node_id = uuid.uuid4()
    uow, assets, attachments, storage = _make_uow_and_repos()

    fired: list[str] = []
    original_commit = uow.commit

    async def _tracking_commit() -> None:
        assert len(assets._assets) == 1
        assert len(attachments._store) == 1
        fired.append("commit")
        await original_commit()

    uow.commit = _tracking_commit  # type: ignore[method-assign]

    use_case = UploadAndAttachMedia(
        uow,
        storage,
        _AllowAllPolicy(),
        InMemoryImageProcessor(),
    )
    await use_case.handle(
        UploadAndAttachMediaCommand(
            filename="doc.pdf",
            content_type="application/pdf",
            stream=_stream(b"pdf"),
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert fired == ["commit"]


async def test_storage_move_fires_after_commit_not_before() -> None:
    """The STAGED→ATTACHED storage move happens after, not during, the DB commit."""
    node_id = uuid.uuid4()
    uow, _, _, storage = _make_uow_and_repos()

    move_order: list[str] = []
    original_commit = uow.commit

    async def _tracking_commit() -> None:
        move_order.append("db-commit")
        await original_commit()

    uow.commit = _tracking_commit  # type: ignore[method-assign]

    original_move = storage.move

    async def _tracking_move(
        asset_id: uuid.UUID, from_status: MediaStatus, to_status: MediaStatus
    ) -> None:
        move_order.append("storage-move")
        await original_move(asset_id, from_status, to_status)

    storage.move = _tracking_move  # type: ignore[method-assign]

    use_case = UploadAndAttachMedia(
        uow,
        storage,
        _AllowAllPolicy(),
        InMemoryImageProcessor(),
    )
    await use_case.handle(
        UploadAndAttachMediaCommand(
            filename="img.png",
            content_type="image/png",
            stream=_stream(b"px"),
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert move_order == ["db-commit", "storage-move"]


# ── Error path ─────────────────────────────────────────────────────────────────


async def test_policy_violation_propagates_and_no_storage_move() -> None:
    """A policy rejection propagates and no file is ever moved to attached storage.

    The in-memory repos don't undo writes (only a real DB session rolls back),
    but the key invariant — no on_commit callback fires — is fully verifiable
    here: nothing ends up in the "attached" storage bucket.
    """
    node_id = uuid.uuid4()
    uow, _, _, storage = _make_uow_and_repos()
    use_case = UploadAndAttachMedia(
        uow,
        storage,
        _RejectAllPolicy(),
        InMemoryImageProcessor(),
    )

    with pytest.raises(UnsupportedMediaTypeError):
        await use_case.handle(
            UploadAndAttachMediaCommand(
                filename="video.mp4",
                content_type="video/mp4",
                stream=_stream(b"vid"),
                target_type=AttachmentTarget.NODE,
                target_id=node_id,
            ),
            SYSTEM_ACTOR,
        )

    # The on_commit storage-move callback must never have fired.
    attached = [k for k in storage._files if k[1] == "attached"]
    assert attached == []

    # InMemoryUnitOfWork records rollback even though it can't undo in-memory writes.
    assert isinstance(uow, InMemoryUnitOfWork)
    assert uow.rolled_back is True


async def test_attribute_key_forwarded_to_attachment() -> None:
    """attribute_key is passed through to the resulting attachment."""
    node_id = uuid.uuid4()
    uow, _, _, storage = _make_uow_and_repos()
    use_case = UploadAndAttachMedia(
        uow,
        storage,
        _AllowAllPolicy(),
        InMemoryImageProcessor(),
    )

    attachment = await use_case.handle(
        UploadAndAttachMediaCommand(
            filename="thumb.jpg",
            content_type="image/jpeg",
            stream=_stream(b"t"),
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
            attribute_key=AttachmentKey.COVER,
        ),
        SYSTEM_ACTOR,
    )

    assert attachment.attribute_key == AttachmentKey.COVER


async def test_upload_and_attach_moves_thumbnail_to_attached() -> None:
    """When a thumbnail is generated, it moves with the asset to attached storage."""
    node_id = uuid.uuid4()
    uow, assets, _, storage = _make_uow_and_repos()
    use_case = UploadAndAttachMedia(
        uow,
        storage,
        _AllowAllPolicy(),
        InMemoryImageProcessor(),
    )

    attachment = await use_case.handle(
        UploadAndAttachMediaCommand(
            filename="photo.jpg",
            content_type="image/jpeg",
            sniffed_content_type="image/jpeg",
            stream=_stream(b"real-image-bytes"),
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    asset = await assets.get(attachment.asset_id)
    assert asset is not None
    assert asset.has_thumbnail is True
    assert (asset.id, "attached") in storage._thumbnails
    assert (asset.id, "staged") not in storage._thumbnails
