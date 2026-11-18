"""The graph module's view of covers: thumbnail URLs for a page of items."""

import uuid

from app.entrypoints.api.shared.bridges.item_covers import MediaItemCovers
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import make_in_memory_repos
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import AttachmentKey, MediaAttachment
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR


async def _cover(
    assets: InMemoryMediaAssetRepository,
    attachments: InMemoryMediaAttachmentRepository,
    node_id: uuid.UUID,
    *,
    thumbnail: bool,
) -> MediaAsset:
    asset = MediaAsset.create(
        owner_id=SYSTEM_ACTOR.id,
        filename="f.jpg",
        content_type="image/jpeg",
        size=1,
        sha256="x",
    )
    asset.has_thumbnail = thumbnail
    await assets.add(asset)
    await attachments.add(
        MediaAttachment.for_node(
            asset_id=asset.id, node_id=node_id, attribute_key=AttachmentKey.COVER
        )
    )
    return asset


async def test_gives_the_thumbnail_url_of_each_cover() -> None:
    """An item with a cover maps to where its thumbnail is served."""
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository(assets)
    covers = MediaItemCovers(
        make_in_memory_repos(assets=assets, attachments=attachments),
        InMemoryAccessGuard(),
    )
    node_id = uuid.uuid4()
    asset = await _cover(assets, attachments, node_id, thumbnail=True)

    found = await covers.thumbnails([node_id, uuid.uuid4()], SYSTEM_ACTOR)

    assert found == {node_id: f"/api/v1/media/{asset.id}/thumbnail"}


async def test_leaves_out_a_cover_with_no_thumbnail() -> None:
    """Without a thumbnail there is nothing small to show, so the item is left out."""
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository(assets)
    covers = MediaItemCovers(
        make_in_memory_repos(assets=assets, attachments=attachments),
        InMemoryAccessGuard(),
    )
    node_id = uuid.uuid4()
    await _cover(assets, attachments, node_id, thumbnail=False)

    assert await covers.thumbnails([node_id], SYSTEM_ACTOR) == {}
