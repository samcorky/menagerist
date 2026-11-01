"""The retention purge end to end on Postgres, rolled back after the test."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.purge_deleted import (
    PurgeDeletedContentCommand,
    PurgeDeletedContentResult,
    build_purge_deleted_content_on,
)
from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.adapters.persistence.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from app.modules.collections.adapters.persistence.models import (
    CollectionMemberModel,
    CollectionModel,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.models import EdgeModel, NodeModel
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.adapters.persistence.media_attachment_repository import (
    SqlAlchemyMediaAttachmentRepository,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import MediaAttachment
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
NOW = datetime.now(UTC)
CUTOFF = NOW - timedelta(days=30)
LONG_AGO = NOW - timedelta(days=31)
MINUTE_AGO = NOW - timedelta(minutes=1)


@pytest_asyncio.fixture
async def factory(postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions that share one outer transaction, rolled back after the test."""
    engine = create_async_engine(postgres_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        await transaction.rollback()
    await engine.dispose()


async def _count(factory: async_sessionmaker[AsyncSession], model: type[object]) -> int:
    async with factory() as session:
        stmt = select(func.count()).select_from(model)
        return (await session.execute(stmt)).scalar_one()


async def test_a_full_run_on_postgres_purges_old_content_and_is_idempotent(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Old rows of both owners, their dependents and files go; the rest stays."""
    storage = InMemoryMediaStorage()
    async with factory() as session:
        nodes = SqlAlchemyNodeRepository(session)
        edges = SqlAlchemyEdgeRepository(session)
        old_a = Node.create(owner_id=ALICE, name="Old A", type=None)
        old_b = Node.create(owner_id=BOB, name="Old B", type=None)
        recent = Node.create(owner_id=ALICE, name="Recent", type=None)
        live = Node.create(owner_id=ALICE, name="Live", type=None)
        old_a.deleted_at = old_b.deleted_at = LONG_AGO
        recent.deleted_at = MINUTE_AGO
        for node in (old_a, old_b, recent, live):
            await nodes.add(node)
        on_old = Edge.create(
            owner_id=ALICE, source_id=old_a.id, target_id=live.id, type="knows"
        )
        own = Edge.create(
            owner_id=ALICE, source_id=live.id, target_id=recent.id, type="knows"
        )
        own.deleted_at = LONG_AGO
        for edge in (on_old, own):
            await edges.add(edge)

        shelves = SqlAlchemyCollectionRepository(session)
        old_shelf = Collection.create(name="Old", slug=Slug("old"), owner_id=BOB)
        old_shelf.deleted_at = LONG_AGO
        live_shelf = Collection.create(name="Live", slug=Slug("live"), owner_id=ALICE)
        for shelf in (old_shelf, live_shelf):
            await shelves.add(shelf)
        members = SqlAlchemyMembershipRepository(session)
        for shelf in (old_shelf, live_shelf):
            await members.add(
                Membership(collection_id=shelf.id, item_id=old_a.id, added_at=NOW)
            )

        asset = MediaAsset.create(
            owner_id=ALICE,
            filename="a.png",
            content_type="image/png",
            size=1,
            sha256="x",
        )
        asset.promote()
        await SqlAlchemyMediaAssetRepository(session).add(asset)
        await SqlAlchemyMediaAttachmentRepository(session).add(
            MediaAttachment.for_node(asset_id=asset.id, node_id=old_a.id)
        )
        storage._files[(asset.id, MediaStatus.ATTACHED.value)] = b"data"
        await session.commit()

    purge = build_purge_deleted_content_on(factory, storage)
    command = PurgeDeletedContentCommand(older_than=CUTOFF, dry_run=True)
    expected = PurgeDeletedContentResult(items=2, connections=1, collections=1)

    assert await purge.handle(command, SYSTEM_ACTOR) == expected
    assert await _count(factory, NodeModel) == 4
    assert (asset.id, MediaStatus.ATTACHED.value) in storage._files

    command.dry_run = False
    assert await purge.handle(command, SYSTEM_ACTOR) == expected

    async with factory() as session:
        remaining = set((await session.execute(select(NodeModel.id))).scalars())
        left_edges = set((await session.execute(select(EdgeModel.id))).scalars())
        left_shelves = set(
            (await session.execute(select(CollectionModel.id))).scalars()
        )
    assert remaining == {recent.id, live.id}
    assert left_edges == set()  # the live one touched the purged item
    assert left_shelves == {live_shelf.id}
    assert await _count(factory, CollectionMemberModel) == 0
    assert storage._files == {}

    assert await purge.handle(command, SYSTEM_ACTOR) == PurgeDeletedContentResult(
        items=0, connections=0, collections=0
    )
