"""Tests for DetachMedia — remove an attachment and orphan if unreferenced."""

import uuid

import pytest

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
from app.modules.media.application.detach_media import DetachMedia, DetachMediaCommand
from app.modules.media.domain.errors import MediaAttachmentNotFoundError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import AttachmentTarget, MediaAttachment
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_attached_asset() -> MediaAsset:
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    return asset


def _make_use_case() -> tuple[
    DetachMedia,
    InMemoryMediaAssetRepository,
    InMemoryMediaAttachmentRepository,
    InMemoryMediaStorage,
]:
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository()
    storage = InMemoryMediaStorage()
    repos = make_in_memory_repos(assets=assets, attachments=attachments)
    uow = create_in_memory_media_uow(repos)
    return DetachMedia(uow, storage), assets, attachments, storage


async def test_detach_removes_attachment_and_orphans_asset() -> None:
    """Detach removes the attachment and orphans the asset when none remain."""
    use_case, assets, attachments, storage = _make_use_case()

    asset = _make_attached_asset()
    await assets.add(asset)
    node_id = uuid.uuid4()
    attachment = MediaAttachment.for_node(asset_id=asset.id, node_id=node_id)
    await attachments.add(attachment)
    storage._files[(asset.id, "attached")] = b"data"

    await use_case.handle(
        DetachMediaCommand(
            asset_id=asset.id,
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert attachment.id not in attachments._store
    assert asset.status is MediaStatus.ORPHANED
    assert storage._files.get((asset.id, "orphaned")) == b"data"
    assert (asset.id, "attached") not in storage._files


async def test_detach_does_not_orphan_when_other_attachments_remain() -> None:
    """Detach leaves the asset attached when other attachment rows still exist."""
    use_case, assets, attachments, _ = _make_use_case()

    asset = _make_attached_asset()
    await assets.add(asset)
    node_a = uuid.uuid4()
    node_b = uuid.uuid4()
    att_a = MediaAttachment.for_node(asset_id=asset.id, node_id=node_a)
    att_b = MediaAttachment.for_node(asset_id=asset.id, node_id=node_b)
    await attachments.add(att_a)
    await attachments.add(att_b)

    await use_case.handle(
        DetachMediaCommand(
            asset_id=asset.id,
            target_type=AttachmentTarget.NODE,
            target_id=node_a,
        ),
        SYSTEM_ACTOR,
    )

    assert att_a.id not in attachments._store
    assert att_b.id in attachments._store
    assert asset.status is MediaStatus.ATTACHED


async def test_detach_skips_orphan_when_asset_missing() -> None:
    """Detach completes without error when the asset row has already been deleted."""
    use_case, _, attachments, _ = _make_use_case()

    node_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    attachment = MediaAttachment.for_node(asset_id=asset_id, node_id=node_id)
    await attachments.add(attachment)

    await use_case.handle(
        DetachMediaCommand(
            asset_id=asset_id,
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert attachment.id not in attachments._store


async def test_detach_raises_when_attachment_not_found() -> None:
    """DetachMedia raises MediaAttachmentNotFoundError when the attachment is absent."""
    use_case, _, _, _ = _make_use_case()

    with pytest.raises(MediaAttachmentNotFoundError):
        await use_case.handle(
            DetachMediaCommand(
                asset_id=uuid.uuid4(),
                target_type=AttachmentTarget.NODE,
                target_id=uuid.uuid4(),
            ),
            SYSTEM_ACTOR,
        )
