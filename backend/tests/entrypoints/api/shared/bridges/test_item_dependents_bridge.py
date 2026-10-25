import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.item_dependents import ItemDependentsPurger
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_in_memory_collections_uow,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import MediaAttachment
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.media.ports.unit_of_work import MediaRepos

OWNER = uuid.UUID(int=1)


async def _asset(repos: MediaRepos, storage: InMemoryMediaStorage) -> MediaAsset:
    asset = MediaAsset.create(
        owner_id=OWNER, filename="a.png", content_type="image/png", size=1, sha256="x"
    )
    asset.promote()
    await repos.assets.add(asset)
    storage._files[(asset.id, MediaStatus.ATTACHED.value)] = b"data"
    return asset


async def test_purging_an_item_clears_memberships_and_only_its_own_media() -> None:
    """The item leaves every collection; an asset another item uses stays."""
    media, storage = make_in_memory_repos(), InMemoryMediaStorage()
    collections = InMemoryCollectionRepository()
    members = InMemoryMembershipRepository(collections)
    repos = CollectionsRepos(collections=collections, memberships=members)
    item, other_item = uuid.uuid7(), uuid.uuid7()
    shelf = Collection.create(name="Shelf", slug=Slug("shelf"), owner_id=OWNER)
    await collections.add(shelf)
    for member in (item, other_item):
        await members.add(
            Membership(
                collection_id=shelf.id, item_id=member, added_at=datetime.now(UTC)
            )
        )
    own, shared = await _asset(media, storage), await _asset(media, storage)
    await media.attachments.add(MediaAttachment.for_node(asset_id=own.id, node_id=item))
    await media.attachments.add(
        MediaAttachment.for_node(asset_id=shared.id, node_id=item)
    )
    await media.attachments.add(
        MediaAttachment.for_node(asset_id=shared.id, node_id=other_item)
    )

    @asynccontextmanager
    async def read() -> AsyncIterator[MediaRepos]:
        yield media

    purger = ItemDependentsPurger(
        guard=get_access_guard(),
        storage=storage,
        collections_uow=lambda: create_in_memory_collections_uow(repos),
        media_uow=lambda: create_in_memory_media_uow(media),
        media_read=read,
    )

    await purger.purge_for_item(item)

    everyone = ContentFilter.everyone()
    assert await members.item_ids(shelf.id, scope=everyone) == {other_item}
    assert await media.assets.get(own.id, scope=everyone) is None
    assert await media.assets.get(shared.id, scope=everyone) is shared
    assert set(storage._files) == {(shared.id, MediaStatus.ATTACHED.value)}
    assert (
        await media.attachments.list_for_target(
            MediaAttachment.for_node(asset_id=own.id, node_id=item).target_type,
            item,
            scope=everyone,
        )
        == []
    )
