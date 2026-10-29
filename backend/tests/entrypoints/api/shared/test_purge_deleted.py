"""The retention purge composed across graph, collections and media in memory."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.item_dependents import ItemDependentsPurger
from app.entrypoints.api.shared.purge_deleted import (
    PurgeDeletedContent,
    PurgeDeletedContentCommand,
    PurgeDeletedContentResult,
)
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_in_memory_collections_uow,
)
from app.modules.collections.application.purge_expired_collections import (
    PurgeExpiredCollections,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
    create_in_memory_graph_uow,
)
from app.modules.graph.application.purge_expired_nodes import PurgeExpiredNodes
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import MediaAttachment
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.media.ports.unit_of_work import MediaRepos

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
NOW = datetime.now(UTC)
CUTOFF = NOW - timedelta(days=30)
LONG_AGO = NOW - timedelta(days=31)
MINUTE_AGO = NOW - timedelta(minutes=1)
EVERYONE = ContentFilter.everyone()


class _World:
    """In-memory graph, collections and media wired through the real bridge."""

    def __init__(self) -> None:
        self.graph = build_in_memory_graph_repos()
        self.collections = InMemoryCollectionRepository()
        self.members = InMemoryMembershipRepository(self.collections)
        self.media = make_in_memory_repos()
        self.storage = InMemoryMediaStorage()
        collections_repos = CollectionsRepos(
            collections=self.collections, memberships=self.members
        )
        guard = get_access_guard()

        @asynccontextmanager
        async def read() -> AsyncIterator[MediaRepos]:
            yield self.media

        purger = ItemDependentsPurger(
            guard=guard,
            storage=self.storage,
            collections_uow=lambda: create_in_memory_collections_uow(collections_repos),
            media_uow=lambda: create_in_memory_media_uow(self.media),
            media_read=read,
        )
        self.purge = PurgeDeletedContent(
            PurgeExpiredNodes(create_in_memory_graph_uow(self.graph), guard, purger),
            PurgeExpiredCollections(
                create_in_memory_collections_uow(collections_repos), guard
            ),
        )

    async def item(
        self, name: str, *, owner: uuid.UUID = ALICE, deleted_at: datetime | None = None
    ) -> Node:
        node = Node.create(owner_id=owner, name=name, type=None)
        node.deleted_at = deleted_at
        await self.graph.nodes.add(node)
        return node

    async def shelf(
        self, name: str, *, owner: uuid.UUID = ALICE, deleted_at: datetime | None = None
    ) -> Collection:
        shelf = Collection.create(name=name, slug=Slug(name), owner_id=owner)
        shelf.deleted_at = deleted_at
        await self.collections.add(shelf)
        return shelf

    async def attach(self, item: Node) -> MediaAsset:
        asset = MediaAsset.create(
            owner_id=item.owner_id or ALICE,
            filename="a.png",
            content_type="image/png",
            size=1,
            sha256="x",
        )
        asset.promote()
        await self.media.assets.add(asset)
        await self.media.attachments.add(
            MediaAttachment.for_node(asset_id=asset.id, node_id=item.id)
        )
        self.storage._files[(asset.id, MediaStatus.ATTACHED.value)] = b"data"
        return asset

    async def run(self, *, dry_run: bool = False) -> PurgeDeletedContentResult:
        return await self.purge.handle(
            PurgeDeletedContentCommand(older_than=CUTOFF, dry_run=dry_run),
            SYSTEM_ACTOR,
        )


async def test_a_full_run_purges_old_content_of_every_owner_and_nothing_else() -> None:
    """Items, their dependents and files, connections and collections go together."""
    w = _World()
    old_a = await w.item("Old A", deleted_at=LONG_AGO)
    old_b = await w.item("Old B", owner=BOB, deleted_at=LONG_AGO)
    recent = await w.item("Recent", deleted_at=MINUTE_AGO)
    live = await w.item("Live")
    own_file = await w.attach(old_a)
    kept_file = await w.attach(live)
    shared = await w.attach(old_b)
    await w.media.attachments.add(
        MediaAttachment.for_node(asset_id=shared.id, node_id=live.id)
    )
    old_shelf = await w.shelf("Old shelf", deleted_at=LONG_AGO)
    recent_shelf = await w.shelf("Recent shelf", deleted_at=MINUTE_AGO)
    live_shelf = await w.shelf("Live shelf")
    for shelf in (old_shelf, recent_shelf, live_shelf):
        for member in (old_a, live):
            await w.members.add(
                Membership(collection_id=shelf.id, item_id=member.id, added_at=NOW)
            )
    on_old = Edge.create(
        owner_id=ALICE, source_id=old_a.id, target_id=live.id, type="knows"
    )
    own = Edge.create(
        owner_id=ALICE, source_id=live.id, target_id=recent.id, type="knows"
    )
    own.deleted_at = LONG_AGO
    for edge in (on_old, own):
        await w.graph.edges.add(edge)

    result = await w.run()

    assert result == PurgeDeletedContentResult(items=2, connections=1, collections=1)
    assert await w.graph.nodes.get_deleted(old_a.id, scope=EVERYONE) is None
    assert await w.graph.nodes.get_deleted(old_b.id, scope=EVERYONE) is None
    assert await w.graph.nodes.get_deleted(recent.id, scope=EVERYONE) is not None
    assert await w.graph.nodes.get(live.id, scope=EVERYONE) is not None
    assert await w.graph.edges.get(on_old.id, scope=EVERYONE) is None
    assert set(w.collections._collections) == {recent_shelf.id, live_shelf.id}
    # Files only the purged items used go; one a live item still uses stays.
    assert await w.media.assets.get(own_file.id, scope=EVERYONE) is None
    assert (own_file.id, MediaStatus.ATTACHED.value) not in w.storage._files
    assert await w.media.assets.get(kept_file.id, scope=EVERYONE) is not None
    assert await w.media.assets.get(shared.id, scope=EVERYONE) is not None
    assert (shared.id, MediaStatus.ATTACHED.value) in w.storage._files
    assert (kept_file.id, MediaStatus.ATTACHED.value) in w.storage._files
    # Memberships of the purged item and collection are gone, live ones stay.
    assert await w.members.collection_ids_for(old_a.id, scope=EVERYONE) == set()
    assert await w.members.collection_ids_for(live.id, scope=EVERYONE) == {
        recent_shelf.id,
        live_shelf.id,
    }


async def test_a_dry_run_reports_the_same_counts_and_changes_nothing() -> None:
    """Counts match the real run; rows, memberships and files stay."""
    w = _World()
    old = await w.item("Old", deleted_at=LONG_AGO)
    asset = await w.attach(old)
    shelf = await w.shelf("Shelf", deleted_at=LONG_AGO)
    await w.members.add(
        Membership(collection_id=shelf.id, item_id=old.id, added_at=NOW)
    )

    dry = await w.run(dry_run=True)

    assert dry == PurgeDeletedContentResult(items=1, connections=0, collections=1)
    assert await w.graph.nodes.get_deleted(old.id, scope=EVERYONE) is not None
    assert shelf.id in w.collections._collections
    assert await w.media.assets.get(asset.id, scope=EVERYONE) is not None
    assert (asset.id, MediaStatus.ATTACHED.value) in w.storage._files
    assert await w.run() == dry


async def test_a_second_run_is_a_no_op() -> None:
    """Nothing is left for a repeat to purge."""
    w = _World()
    await w.item("Old", deleted_at=LONG_AGO)
    await w.shelf("Old shelf", deleted_at=LONG_AGO)
    await w.run()

    assert await w.run() == PurgeDeletedContentResult(
        items=0, connections=0, collections=0
    )
