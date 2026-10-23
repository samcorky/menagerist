import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.collections.application.purge_collection import (
    PurgeCollection,
    PurgeCollectionCommand,
)
from app.modules.collections.application.purge_item_memberships import (
    PurgeItemMemberships,
    PurgeItemMembershipsCommand,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


async def _put(world: World, collection: Collection, item: uuid.UUID) -> None:
    await world.memberships.add(
        Membership(
            collection_id=collection.id, item_id=item, added_at=datetime.now(UTC)
        )
    )


async def test_purge_collection_removes_it_and_its_memberships_only(
    world: World, make_collection: MakeCollection
) -> None:
    """A soft-deleted collection and its rows go; another collection is untouched."""
    doomed, other = make_collection("Doomed"), make_collection("Other")
    for collection in (doomed, other):
        await world.collections.add(collection)
    item = uuid.uuid7()
    await _put(world, doomed, item)
    await _put(world, other, item)
    doomed.soft_delete()
    await world.collections.save(doomed)

    await PurgeCollection(world.uow, get_access_guard()).handle(
        PurgeCollectionCommand(collection_id=doomed.id), SYSTEM_ACTOR
    )

    everyone = ContentFilter.everyone()
    assert world.uow.committed is True
    assert doomed.id not in world.collections._collections
    assert await world.memberships.collection_ids_for(item, scope=everyone) == {
        other.id
    }


async def test_purge_collection_with_an_unknown_id_is_a_no_op(
    world: World,
) -> None:
    """An id that is already gone does not raise."""
    await PurgeCollection(world.uow, get_access_guard()).handle(
        PurgeCollectionCommand(collection_id=uuid.uuid7()), SYSTEM_ACTOR
    )


async def test_purge_item_memberships_clears_the_item_everywhere(
    world: World, make_collection: MakeCollection
) -> None:
    """A purged item leaves live and soft-deleted collections alike."""
    live, deleted = make_collection("Live"), make_collection("Deleted")
    for collection in (live, deleted):
        await world.collections.add(collection)
    gone, kept = uuid.uuid7(), uuid.uuid7()
    for collection in (live, deleted):
        await _put(world, collection, gone)
    await _put(world, live, kept)
    deleted.soft_delete()
    await world.collections.save(deleted)

    await PurgeItemMemberships(world.uow, get_access_guard()).handle(
        PurgeItemMembershipsCommand(item_id=gone), SYSTEM_ACTOR
    )

    everyone = ContentFilter.everyone()
    assert await world.memberships.collection_ids_for(gone, scope=everyone) == set()
    assert await world.memberships.item_ids(live.id, scope=everyone) == {kept}
