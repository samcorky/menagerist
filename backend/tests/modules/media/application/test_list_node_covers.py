"""Tests for ListNodeCovers - the cover of each of several items, in one call."""

import uuid

from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import make_in_memory_repos
from app.modules.media.application.list_node_covers import (
    ListNodeCovers,
    ListNodeCoversQuery,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import AttachmentKey, MediaAttachment
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR


def _asset() -> MediaAsset:
    return MediaAsset.create(
        owner_id=SYSTEM_ACTOR.id,
        filename="f.jpg",
        content_type="image/jpeg",
        size=1,
        sha256="x",
    )


def _use_case() -> tuple[
    ListNodeCovers, InMemoryMediaAssetRepository, InMemoryMediaAttachmentRepository
]:
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository(assets)
    repos = make_in_memory_repos(assets=assets, attachments=attachments)
    return ListNodeCovers(repos, InMemoryAccessGuard()), assets, attachments


async def _attach(
    assets: InMemoryMediaAssetRepository,
    attachments: InMemoryMediaAttachmentRepository,
    node_id: uuid.UUID,
    key: AttachmentKey | None,
) -> MediaAsset:
    asset = _asset()
    await assets.add(asset)
    await attachments.add(
        MediaAttachment.for_node(asset_id=asset.id, node_id=node_id, attribute_key=key)
    )
    return asset


async def test_returns_the_cover_of_each_item_that_has_one() -> None:
    """Each item asked about maps to its cover asset; items without one are left out."""
    use_case, assets, attachments = _use_case()
    with_cover, other_cover, bare = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first = await _attach(assets, attachments, with_cover, AttachmentKey.COVER)
    second = await _attach(assets, attachments, other_cover, AttachmentKey.COVER)

    result = await use_case.handle(
        ListNodeCoversQuery(node_ids=[with_cover, other_cover, bare]), SYSTEM_ACTOR
    )

    assert {node: asset.id for node, asset in result.items()} == {
        with_cover: first.id,
        other_cover: second.id,
    }


async def test_ignores_attachments_that_are_not_the_cover() -> None:
    """A photo that is not the cover does not stand in for one."""
    use_case, assets, attachments = _use_case()
    node_id = uuid.uuid4()
    await _attach(assets, attachments, node_id, None)

    query = ListNodeCoversQuery(node_ids=[node_id])
    result = await use_case.handle(query, SYSTEM_ACTOR)

    assert result == {}


async def test_ignores_items_not_asked_about() -> None:
    """Only the items named come back."""
    use_case, assets, attachments = _use_case()
    asked, other = uuid.uuid4(), uuid.uuid4()
    await _attach(assets, attachments, other, AttachmentKey.COVER)

    result = await use_case.handle(ListNodeCoversQuery(node_ids=[asked]), SYSTEM_ACTOR)

    assert result == {}


async def test_no_items_means_no_covers() -> None:
    """An empty page asks nothing and returns nothing."""
    use_case, _, _ = _use_case()

    assert await use_case.handle(ListNodeCoversQuery(node_ids=[]), SYSTEM_ACTOR) == {}
