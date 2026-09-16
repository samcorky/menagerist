"""Tests for ListNodeMedia — fetch all assets attached to a node."""

import uuid

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
from app.modules.media.application.list_node_media import (
    ListNodeMedia,
    ListNodeMediaQuery,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import AttachmentKey, MediaAttachment
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_asset(filename: str = "f.jpg") -> MediaAsset:
    return MediaAsset.create(
        filename=filename, content_type="image/jpeg", size=1, sha256="x"
    )


def _make_use_case() -> tuple[
    ListNodeMedia, InMemoryMediaAssetRepository, InMemoryMediaAttachmentRepository
]:
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository()
    repos = make_in_memory_repos(assets=assets, attachments=attachments)
    uow = create_in_memory_media_uow(repos)
    return ListNodeMedia(uow), assets, attachments


async def test_list_node_media_returns_attached_assets() -> None:
    """ListNodeMedia returns assets linked to the specified node."""
    use_case, assets, attachments = _make_use_case()

    node_id = uuid.uuid4()
    asset = _make_asset()
    await assets.add(asset)
    await attachments.add(MediaAttachment.for_node(asset_id=asset.id, node_id=node_id))

    result = await use_case.handle(ListNodeMediaQuery(node_id=node_id), SYSTEM_ACTOR)

    assert len(result) == 1
    assert result[0].asset.id == asset.id
    assert result[0].attribute_key is None


async def test_list_node_media_preserves_attribute_key() -> None:
    """ListNodeMedia includes the attachment's attribute_key in each result."""
    use_case, assets, attachments = _make_use_case()

    node_id = uuid.uuid4()
    asset = _make_asset()
    await assets.add(asset)
    await attachments.add(
        MediaAttachment.for_node(
            asset_id=asset.id, node_id=node_id, attribute_key=AttachmentKey.COVER
        )
    )

    result = await use_case.handle(ListNodeMediaQuery(node_id=node_id), SYSTEM_ACTOR)

    assert result[0].attribute_key is AttachmentKey.COVER


async def test_list_node_media_returns_empty_for_unattached_node() -> None:
    """ListNodeMedia returns an empty list when no assets are attached."""
    use_case, _, _ = _make_use_case()

    result = await use_case.handle(
        ListNodeMediaQuery(node_id=uuid.uuid4()), SYSTEM_ACTOR
    )

    assert result == []


async def test_list_node_media_skips_dangling_attachments() -> None:
    """ListNodeMedia silently skips attachments whose asset has been deleted."""
    use_case, _, attachments = _make_use_case()

    node_id = uuid.uuid4()
    orphan_attachment = MediaAttachment.for_node(asset_id=uuid.uuid4(), node_id=node_id)
    await attachments.add(orphan_attachment)

    result = await use_case.handle(ListNodeMediaQuery(node_id=node_id), SYSTEM_ACTOR)

    assert result == []


async def test_list_node_media_excludes_other_nodes() -> None:
    """ListNodeMedia only returns assets for the queried node, not other nodes."""
    use_case, assets, attachments = _make_use_case()

    node_a = uuid.uuid4()
    node_b = uuid.uuid4()
    asset_a = _make_asset("a.jpg")
    asset_b = _make_asset("b.jpg")
    await assets.add(asset_a)
    await assets.add(asset_b)
    await attachments.add(MediaAttachment.for_node(asset_id=asset_a.id, node_id=node_a))
    await attachments.add(MediaAttachment.for_node(asset_id=asset_b.id, node_id=node_b))

    result = await use_case.handle(ListNodeMediaQuery(node_id=node_a), SYSTEM_ACTOR)

    assert len(result) == 1
    assert result[0].asset.id == asset_a.id
