"""Tests for ClearMediaCover — the regression coverage for the cover-detach bug."""

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
from app.modules.media.application.clear_media_cover import (
    ClearMediaCover,
    ClearMediaCoverCommand,
)
from app.modules.media.domain.errors import MediaAttachmentNotFoundError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_attached_asset() -> MediaAsset:
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    return asset


def _make_use_case() -> tuple[
    ClearMediaCover, InMemoryMediaAssetRepository, InMemoryMediaAttachmentRepository
]:
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository()
    repos = make_in_memory_repos(assets=assets, attachments=attachments)
    uow = create_in_memory_media_uow(repos)
    return ClearMediaCover(uow), assets, attachments


async def test_clear_cover_keeps_asset_attached() -> None:
    """Clearing the cover flag leaves the attachment row and asset status intact.

    Regression test: removing cover status via the UI must not detach the
    asset from the node (previously accomplished by calling detach_media,
    which orphans the asset once its last attachment row is gone).
    """
    use_case, assets, attachments = _make_use_case()

    asset = _make_attached_asset()
    await assets.add(asset)
    node_id = uuid.uuid4()
    attachment = MediaAttachment.for_node(
        asset_id=asset.id, node_id=node_id, attribute_key=AttachmentKey.COVER
    )
    await attachments.add(attachment)

    await use_case.handle(
        ClearMediaCoverCommand(
            asset_id=asset.id,
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert attachment.id in attachments._store
    assert attachments._store[attachment.id].attribute_key is None
    assert asset.status is MediaStatus.ATTACHED


async def test_clear_cover_raises_when_not_cover() -> None:
    """ClearMediaCover raises MediaAttachmentNotFoundError if not currently cover."""
    use_case, assets, attachments = _make_use_case()

    asset = _make_attached_asset()
    await assets.add(asset)
    node_id = uuid.uuid4()
    await attachments.add(MediaAttachment.for_node(asset_id=asset.id, node_id=node_id))

    with pytest.raises(MediaAttachmentNotFoundError):
        await use_case.handle(
            ClearMediaCoverCommand(
                asset_id=asset.id,
                target_type=AttachmentTarget.NODE,
                target_id=node_id,
            ),
            SYSTEM_ACTOR,
        )
