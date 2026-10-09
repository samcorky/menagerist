"""Tests for AttachMedia - the single-asset attach handler."""

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
from app.modules.media.application.attach_media import AttachMedia, AttachMediaCommand
from app.modules.media.domain.errors import (
    CoverAlreadySetError,
    MediaAssetNotFoundError,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.shared_kernel.actor import SYSTEM_ACTOR


class _AllowAll:
    async def check(self, target: AttachmentTarget, asset: MediaAsset) -> None:
        pass


def _make_use_case() -> tuple[
    AttachMedia,
    InMemoryMediaAssetRepository,
    InMemoryMediaAttachmentRepository,
    InMemoryMediaStorage,
]:
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository()
    storage = InMemoryMediaStorage()
    repos = make_in_memory_repos(assets=assets, attachments=attachments)
    uow = create_in_memory_media_uow(repos)
    return AttachMedia(uow, storage, _AllowAll()), assets, attachments, storage


async def test_attach_raises_when_asset_not_found() -> None:
    """AttachMedia raises MediaAssetNotFoundError when the asset id is unknown."""
    use_case, _, _, _ = _make_use_case()

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(
            AttachMediaCommand(
                asset_id=uuid.uuid4(),
                target_type=AttachmentTarget.NODE,
                target_id=uuid.uuid4(),
            ),
            SYSTEM_ACTOR,
        )


async def test_attach_already_attached_asset_skips_storage_move() -> None:
    """Attaching an ATTACHED asset creates a new attachment row but no storage move."""
    use_case, assets, _, storage = _make_use_case()

    asset = MediaAsset.create(
        filename="photo.jpg", content_type="image/jpeg", size=10, sha256="a"
    )
    asset.promote()
    await assets.add(asset)

    node_id = uuid.uuid4()
    attachment = await use_case.handle(
        AttachMediaCommand(
            asset_id=asset.id,
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
        ),
        SYSTEM_ACTOR,
    )

    assert attachment.target_id == node_id
    assert asset.status is MediaStatus.ATTACHED
    assert (asset.id, "staged") not in storage._files
    assert (asset.id, "attached") not in storage._files


async def _staged_image(
    assets: InMemoryMediaAssetRepository, storage: InMemoryMediaStorage
) -> MediaAsset:
    asset = MediaAsset.create(
        filename="c.png", content_type="image/png", size=1, sha256="c"
    )
    await assets.add(asset)
    storage._files[(asset.id, "staged")] = b"px"
    return asset


async def test_attach_as_cover_succeeds_when_target_has_no_cover() -> None:
    """A first cover attaches and carries the cover key."""
    use_case, assets, _, storage = _make_use_case()
    asset = await _staged_image(assets, storage)

    attachment = await use_case.handle(
        AttachMediaCommand(
            asset_id=asset.id,
            target_type=AttachmentTarget.NODE,
            target_id=uuid.uuid4(),
            attribute_key=AttachmentKey.COVER,
        ),
        SYSTEM_ACTOR,
    )

    assert attachment.attribute_key is AttachmentKey.COVER


async def test_attach_as_cover_raises_when_target_already_has_cover() -> None:
    """A second cover is refused before anything is promoted or written."""
    use_case, assets, attachments, storage = _make_use_case()
    node_id = uuid.uuid4()
    existing = MediaAttachment.for_node(
        asset_id=uuid.uuid4(), node_id=node_id, attribute_key=AttachmentKey.COVER
    )
    await attachments.add(existing)
    asset = await _staged_image(assets, storage)

    with pytest.raises(CoverAlreadySetError, match="already has a cover"):
        await use_case.handle(
            AttachMediaCommand(
                asset_id=asset.id,
                target_type=AttachmentTarget.NODE,
                target_id=node_id,
                attribute_key=AttachmentKey.COVER,
            ),
            SYSTEM_ACTOR,
        )

    assert asset.status is MediaStatus.STAGED
    assert len(await attachments.list_for_target(AttachmentTarget.NODE, node_id)) == 1
    assert (asset.id, "attached") not in storage._files


async def test_attach_without_key_is_allowed_when_target_has_cover() -> None:
    """Only a cover attach is refused; plain attachments still pile up."""
    use_case, assets, attachments, storage = _make_use_case()
    node_id = uuid.uuid4()
    await attachments.add(
        MediaAttachment.for_node(
            asset_id=uuid.uuid4(), node_id=node_id, attribute_key=AttachmentKey.COVER
        )
    )
    asset = await _staged_image(assets, storage)

    await use_case.handle(
        AttachMediaCommand(
            asset_id=asset.id, target_type=AttachmentTarget.NODE, target_id=node_id
        ),
        SYSTEM_ACTOR,
    )

    assert len(await attachments.list_for_target(AttachmentTarget.NODE, node_id)) == 2
