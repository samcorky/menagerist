"""Tests for SetMediaCover — atomically move the cover flag between attachments."""

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
from app.modules.media.application.set_media_cover import (
    SetMediaCover,
    SetMediaCoverCommand,
)
from app.modules.media.domain.errors import (
    MediaAssetNotFoundError,
    MediaAttachmentNotFoundError,
    UnsupportedMediaTypeError,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_image_asset() -> MediaAsset:
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    return asset


def _make_use_case() -> tuple[
    SetMediaCover, InMemoryMediaAssetRepository, InMemoryMediaAttachmentRepository
]:
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository()
    repos = make_in_memory_repos(assets=assets, attachments=attachments)
    uow = create_in_memory_media_uow(repos)
    return SetMediaCover(uow), assets, attachments


async def test_set_cover_atomically_unsets_previous_cover() -> None:
    """Setting a new cover clears the previous cover holder's flag, not its row."""
    use_case, assets, attachments = _make_use_case()

    node_id = uuid.uuid4()
    old_cover_asset = _make_image_asset()
    new_cover_asset = _make_image_asset()
    await assets.add(old_cover_asset)
    await assets.add(new_cover_asset)

    old_attachment = MediaAttachment.for_node(
        asset_id=old_cover_asset.id, node_id=node_id, attribute_key=AttachmentKey.COVER
    )
    new_attachment = MediaAttachment.for_node(
        asset_id=new_cover_asset.id, node_id=node_id
    )
    await attachments.add(old_attachment)
    await attachments.add(new_attachment)

    result = await use_case.handle(
        SetMediaCoverCommand(
            asset_id=new_cover_asset.id,
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert result.attribute_key is AttachmentKey.COVER
    assert attachments._store[new_attachment.id].attribute_key is AttachmentKey.COVER
    assert attachments._store[old_attachment.id].attribute_key is None
    # Neither row is removed — only the flag moved.
    assert old_attachment.id in attachments._store
    assert new_attachment.id in attachments._store


async def test_set_cover_leaves_unrelated_attachments_untouched() -> None:
    """A bystander attachment (different asset, no cover flag) is left as-is."""
    use_case, assets, attachments = _make_use_case()

    node_id = uuid.uuid4()
    bystander_asset = _make_image_asset()
    new_cover_asset = _make_image_asset()
    await assets.add(bystander_asset)
    await assets.add(new_cover_asset)

    bystander_attachment = MediaAttachment.for_node(
        asset_id=bystander_asset.id, node_id=node_id
    )
    new_attachment = MediaAttachment.for_node(
        asset_id=new_cover_asset.id, node_id=node_id
    )
    await attachments.add(bystander_attachment)
    await attachments.add(new_attachment)

    await use_case.handle(
        SetMediaCoverCommand(
            asset_id=new_cover_asset.id,
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert attachments._store[bystander_attachment.id].attribute_key is None
    assert attachments._store[new_attachment.id].attribute_key is AttachmentKey.COVER


async def test_set_cover_raises_when_asset_missing() -> None:
    """SetMediaCover raises MediaAssetNotFoundError when the asset doesn't exist."""
    use_case, _, _ = _make_use_case()

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(
            SetMediaCoverCommand(
                asset_id=uuid.uuid4(),
                target_type=AttachmentTarget.NODE,
                target_id=uuid.uuid4(),
            ),
            SYSTEM_ACTOR,
        )


async def test_set_cover_rejects_non_image_asset() -> None:
    """SetMediaCover raises UnsupportedMediaTypeError for non-image assets."""
    use_case, assets, attachments = _make_use_case()

    node_id = uuid.uuid4()
    asset = MediaAsset.create(
        filename="f.pdf", content_type="application/pdf", size=1, sha256="x"
    )
    asset.promote()
    await assets.add(asset)
    await attachments.add(MediaAttachment.for_node(asset_id=asset.id, node_id=node_id))

    with pytest.raises(UnsupportedMediaTypeError):
        await use_case.handle(
            SetMediaCoverCommand(
                asset_id=asset.id,
                target_type=AttachmentTarget.NODE,
                target_id=node_id,
            ),
            SYSTEM_ACTOR,
        )


async def test_set_cover_raises_when_asset_not_attached_to_target() -> None:
    """SetMediaCover raises MediaAttachmentNotFoundError with no existing attachment."""
    use_case, assets, _ = _make_use_case()

    asset = _make_image_asset()
    await assets.add(asset)

    with pytest.raises(MediaAttachmentNotFoundError):
        await use_case.handle(
            SetMediaCoverCommand(
                asset_id=asset.id,
                target_type=AttachmentTarget.NODE,
                target_id=uuid.uuid4(),
            ),
            SYSTEM_ACTOR,
        )
