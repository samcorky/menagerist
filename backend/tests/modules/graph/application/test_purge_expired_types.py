"""The retention purge of soft-deleted item and relationship types."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
    create_in_memory_graph_uow,
)
from app.modules.graph.application.purge_expired_types import (
    PurgeExpiredTypes,
    PurgeExpiredTypesCommand,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ValidationError

NOW = datetime.now(UTC)
CUTOFF = NOW - timedelta(days=30)
LONG_AGO = NOW - timedelta(days=31)
OWNER = uuid.UUID(int=7)


class _World:
    def __init__(self) -> None:
        self.repos = build_in_memory_graph_repos()
        self.purge = PurgeExpiredTypes(
            create_in_memory_graph_uow(self.repos), InMemoryAccessGuard()
        )

    async def run(
        self, *, dry_run: bool = False, batch_size: int = 100
    ) -> tuple[int, int]:
        result = await self.purge.handle(
            PurgeExpiredTypesCommand(
                older_than=CUTOFF, dry_run=dry_run, batch_size=batch_size
            ),
            SYSTEM_ACTOR,
        )
        return result.item_types, result.relationship_types

    async def item_type(self, slug: str, *, deleted_at: datetime | None) -> NodeType:
        node_type = NodeType.create(owner_id=OWNER, slug=slug, label=slug)
        node_type.deleted_at = deleted_at
        await self.repos.node_types.add(node_type)
        return node_type

    async def edge_type(self, slug: str, *, deleted_at: datetime | None) -> EdgeType:
        edge_type = EdgeType.create(owner_id=OWNER, slug=slug, label=slug)
        edge_type.deleted_at = deleted_at
        await self.repos.edge_types.add(edge_type)
        return edge_type

    async def item(self, type_slug: str, *, deleted_at: datetime | None = None) -> None:
        node = Node.create(owner_id=OWNER, name="x", type=type_slug)
        node.deleted_at = deleted_at
        await self.repos.nodes.add(node)

    async def connection(
        self, type_slug: str, *, deleted_at: datetime | None = None
    ) -> None:
        edge = Edge.create(
            owner_id=OWNER,
            source_id=uuid.uuid7(),
            target_id=uuid.uuid7(),
            type=type_slug,
        )
        edge.deleted_at = deleted_at
        await self.repos.edges.add(edge)

    async def remaining(self) -> tuple[int, int]:
        """Soft-deleted item and relationship types still stored."""
        everything = datetime.now(UTC) + timedelta(days=1)
        return (
            len(
                await self.repos.node_types.list_deleted_before(
                    everything, after=None, limit=99
                )
            ),
            len(
                await self.repos.edge_types.list_deleted_before(
                    everything, after=None, limit=99
                )
            ),
        )


async def test_expired_unused_types_are_purged_and_the_rest_kept() -> None:
    """Only types deleted before the cutoff go; live and recent ones stay."""
    w = _World()
    await w.item_type("old", deleted_at=LONG_AGO)
    await w.item_type("recent", deleted_at=NOW)
    live = await w.item_type("live", deleted_at=None)
    await w.edge_type("old-link", deleted_at=LONG_AGO)
    await w.edge_type("recent-link", deleted_at=NOW)
    live_link = await w.edge_type("live-link", deleted_at=None)

    assert await w.run() == (1, 1)

    assert await w.remaining() == (1, 1)
    assert await w.repos.node_types.get(live.id, scope=ContentFilter.everyone()) is live
    assert (
        await w.repos.edge_types.get(live_link.id, scope=ContentFilter.everyone())
        is live_link
    )


@pytest.mark.parametrize("deleted_at", [None, LONG_AGO])
async def test_an_item_type_still_carried_by_an_item_is_kept(
    deleted_at: datetime | None,
) -> None:
    """A live item, or one in Recently deleted, holds its type back."""
    w = _World()
    await w.item_type("books", deleted_at=LONG_AGO)
    await w.item("books", deleted_at=deleted_at)

    assert await w.run() == (0, 0)
    assert await w.remaining() == (1, 0)


@pytest.mark.parametrize("deleted_at", [None, LONG_AGO])
async def test_a_relationship_type_still_carried_by_a_connection_is_kept(
    deleted_at: datetime | None,
) -> None:
    """A live connection, or one in Recently deleted, holds its type back."""
    w = _World()
    await w.edge_type("owns", deleted_at=LONG_AGO)
    await w.connection("owns", deleted_at=deleted_at)

    assert await w.run() == (0, 0)
    assert await w.remaining() == (0, 1)


async def test_a_type_whose_slug_a_live_type_took_over_is_purged() -> None:
    """Items now belong to the live type, so the old row holds nothing back."""
    w = _World()
    await w.item_type("books", deleted_at=LONG_AGO)
    await w.item_type("books", deleted_at=None)
    await w.item("books")
    await w.edge_type("owns", deleted_at=LONG_AGO)
    await w.edge_type("owns", deleted_at=None)
    await w.connection("owns")

    assert await w.run() == (1, 1)


async def test_a_dry_run_counts_without_deleting() -> None:
    """The same count is reported, and nothing is removed."""
    w = _World()
    await w.item_type("old", deleted_at=LONG_AGO)
    await w.edge_type("old-link", deleted_at=LONG_AGO)

    assert await w.run(dry_run=True) == (1, 1)
    assert await w.remaining() == (1, 1)
    assert await w.run() == (1, 1)
    assert await w.remaining() == (0, 0)


async def test_types_left_in_place_do_not_stall_later_batches() -> None:
    """With one type per batch, a kept type is passed over, not retried."""
    w = _World()
    for i in range(3):
        await w.item_type(f"kept-{i}", deleted_at=LONG_AGO)
        await w.item(f"kept-{i}")
        await w.edge_type(f"kept-link-{i}", deleted_at=LONG_AGO)
        await w.connection(f"kept-link-{i}")
    await w.item_type("a", deleted_at=LONG_AGO)
    await w.item_type("b", deleted_at=LONG_AGO)
    await w.edge_type("c", deleted_at=LONG_AGO)

    assert await w.run(batch_size=1) == (2, 1)
    assert await w.remaining() == (3, 3)


def test_the_command_is_validated() -> None:
    """A naive cutoff or an empty batch is refused."""
    with pytest.raises(ValidationError, match="timezone-aware"):
        PurgeExpiredTypesCommand(older_than=datetime(2026, 1, 1))
    with pytest.raises(ValidationError, match="batch_size"):
        PurgeExpiredTypesCommand(older_than=CUTOFF, batch_size=0)
