import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.attach_target_access import (
    GraphAttachTargetAccess,
)
from app.entrypoints.api.shared.bridges.collection_items import GraphItemLookup
from app.entrypoints.api.shared.bridges.item_companions import ItemCompanionCopier
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
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
)
from app.modules.graph.domain.node import Node
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

OWNER = uuid.UUID(int=1)
ACTOR = Actor(id=OWNER, roles=frozenset({"member"}))


async def test_copier_copies_media_and_joins_collections_through_the_use_cases() -> (
    None
):
    """The bridge runs the media and collections use cases for the caller."""
    graph = build_in_memory_graph_repos()
    source = Node.create(owner_id=OWNER, name="Alien")
    target = Node.create(owner_id=OWNER, name="Alien 2")
    await graph.nodes.add(source)
    await graph.nodes.add(target)
    media = make_in_memory_repos()
    asset = MediaAsset.create(
        owner_id=OWNER, filename="a.png", content_type="image/png", size=1, sha256="x"
    )
    asset.promote()
    await media.assets.add(asset)
    storage = InMemoryMediaStorage()
    storage._files[(asset.id, MediaStatus.ATTACHED.value)] = b"data"
    await media.attachments.add(
        MediaAttachment.for_node(
            asset_id=asset.id, node_id=source.id, attribute_key=AttachmentKey.COVER
        )
    )
    collections = InMemoryCollectionRepository()
    members = InMemoryMembershipRepository(collections)
    collection_repos = CollectionsRepos(collections=collections, memberships=members)
    shelf = Collection.create(name="Shelf", slug=Slug("shelf"), owner_id=OWNER)
    await collections.add(shelf)
    await members.add(
        Membership(
            collection_id=shelf.id, item_id=source.id, added_at=datetime.now(UTC)
        )
    )

    @asynccontextmanager
    async def items() -> AsyncIterator[GraphItemLookup]:
        yield GraphItemLookup(graph)

    @asynccontextmanager
    async def targets() -> AsyncIterator[GraphAttachTargetAccess]:
        yield GraphAttachTargetAccess(graph)

    copier = ItemCompanionCopier(
        guard=get_access_guard(),
        storage=storage,
        collections_uow=lambda: create_in_memory_collections_uow(collection_repos),
        media_uow=lambda: create_in_memory_media_uow(media),
        items=items,
        targets=targets,
    )

    await copier.copy_media(
        source.id, target.id, attachments=False, cover=True, actor=ACTOR
    )
    await copier.copy_collections(source.id, target.id, actor=ACTOR)

    copied = await media.attachments.list_for_target(
        AttachmentTarget.NODE, target.id, scope=ContentFilter.of(OWNER)
    )
    assert [a.attribute_key for a in copied] == [AttachmentKey.COVER]
    assert copied[0].asset_id != asset.id
    assert storage._files[(copied[0].asset_id, MediaStatus.ATTACHED.value)] == b"data"
    assert await members.item_ids(shelf.id, scope=ContentFilter.of(OWNER)) == {
        source.id,
        target.id,
    }
