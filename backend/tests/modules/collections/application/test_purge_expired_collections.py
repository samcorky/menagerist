import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.collections.application.purge_expired_collections import (
    PurgeExpiredCollections,
    PurgeExpiredCollectionsCommand,
    PurgeExpiredCollectionsResult,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ForbiddenError, ValidationError

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World

NOW = datetime.now(UTC)
CUTOFF = NOW - timedelta(days=30)
LONG_AGO = NOW - timedelta(days=31)
MINUTE_AGO = NOW - timedelta(minutes=1)
ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


async def _shelf(
    world: World,
    make: MakeCollection,
    name: str,
    *,
    owner: uuid.UUID = ALICE,
    deleted_at: datetime | None = None,
) -> Collection:
    collection = make(name)
    collection.owner_id = owner
    collection.deleted_at = deleted_at
    await world.collections.add(collection)
    return collection


async def _run(
    world: World, *, dry_run: bool = False, batch_size: int = 100
) -> PurgeExpiredCollectionsResult:
    return await PurgeExpiredCollections(world.uow, get_access_guard()).handle(
        PurgeExpiredCollectionsCommand(
            older_than=CUTOFF, dry_run=dry_run, batch_size=batch_size
        ),
        SYSTEM_ACTOR,
    )


async def test_only_old_deleted_collections_of_any_owner_go(
    world: World, make_collection: MakeCollection
) -> None:
    """Old rows of both owners go with their memberships; recent and live stay."""
    old_a = await _shelf(world, make_collection, "Old A", deleted_at=LONG_AGO)
    old_b = await _shelf(
        world, make_collection, "Old B", owner=BOB, deleted_at=LONG_AGO
    )
    recent = await _shelf(world, make_collection, "Recent", deleted_at=MINUTE_AGO)
    live = await _shelf(world, make_collection, "Live")
    item = uuid.uuid7()
    for shelf in (old_a, old_b, live):
        await world.memberships.add(
            Membership(collection_id=shelf.id, item_id=item, added_at=NOW)
        )

    result = await _run(world)

    assert result == PurgeExpiredCollectionsResult(collections=2)
    assert set(world.collections._collections) == {recent.id, live.id}
    everyone = ContentFilter.everyone()
    assert await world.memberships.collection_ids_for(item, scope=everyone) == {live.id}


async def test_dry_run_counts_and_changes_nothing(
    world: World, make_collection: MakeCollection
) -> None:
    """A dry run reports what a real run purges and deletes nothing."""
    await _shelf(world, make_collection, "Old", deleted_at=LONG_AGO)

    dry = await _run(world, dry_run=True)
    assert dry == PurgeExpiredCollectionsResult(collections=1)
    assert len(world.collections._collections) == 1
    assert world.uow.committed is False

    assert await _run(world) == dry
    assert await _run(world) == PurgeExpiredCollectionsResult(collections=0)


async def test_batches_smaller_than_the_backlog_purge_everything(
    world: World, make_collection: MakeCollection
) -> None:
    """Five collections clear in batches of two."""
    for i in range(5):
        await _shelf(world, make_collection, f"Old {i}", deleted_at=LONG_AGO)

    assert await _run(world, batch_size=2) == PurgeExpiredCollectionsResult(
        collections=5
    )
    assert world.collections._collections == {}


async def test_a_collection_restored_since_it_was_listed_is_skipped(
    world: World, make_collection: MakeCollection
) -> None:
    """Restoring between listing and purging keeps the collection."""
    shelf = await _shelf(world, make_collection, "Back", deleted_at=LONG_AGO)
    listed = world.collections.list_deleted_before

    async def restore_after_listing(
        cutoff: datetime, *, limit: int
    ) -> list[Collection]:
        rows = await listed(cutoff, limit=limit)
        shelf.deleted_at = None
        return rows

    world.collections.list_deleted_before = restore_after_listing  # type: ignore[method-assign]

    assert await _run(world) == PurgeExpiredCollectionsResult(collections=0)
    assert shelf.id in world.collections._collections


async def test_only_the_system_actor_may_run_it(world: World) -> None:
    """A person cannot trigger the instance-wide purge."""
    with pytest.raises(ForbiddenError):
        await PurgeExpiredCollections(world.uow, get_access_guard()).handle(
            PurgeExpiredCollectionsCommand(older_than=CUTOFF),
            Actor(id=ALICE, roles=frozenset({"admin"})),
        )


def test_the_command_refuses_a_naive_cutoff_and_an_empty_batch() -> None:
    """A cutoff needs a timezone and a batch needs at least one row."""
    with pytest.raises(ValidationError):
        PurgeExpiredCollectionsCommand(older_than=datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        PurgeExpiredCollectionsCommand(older_than=CUTOFF, batch_size=0)
