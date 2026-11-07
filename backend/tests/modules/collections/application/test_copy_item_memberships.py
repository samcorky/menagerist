"""Tests for the CopyItemMemberships use case."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.modules.collections.application.copy_item_memberships import (
    CopyItemMemberships,
    CopyItemMembershipsCommand,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from tests.modules.collections.conftest import MakeCollection, World


def _handler(world: World) -> CopyItemMemberships:
    """Build the use case over `world`."""
    return CopyItemMemberships(world.uow, InMemoryAccessGuard(), world.items)


async def _put(world: World, collection: Collection, item_id: uuid.UUID) -> None:
    await world.collections.add(collection)
    await world.memberships.add(
        Membership(
            collection_id=collection.id, item_id=item_id, added_at=datetime.now(UTC)
        )
    )


async def _members(world: World, collection: Collection) -> set[uuid.UUID]:
    return await world.memberships.item_ids(
        collection.id, scope=ContentFilter.everyone()
    )


async def test_target_joins_every_manual_collection_of_the_source(
    world: World, make_collection: MakeCollection
) -> None:
    """The copy lands on each shelf its original is on, and the original stays."""
    source, target = uuid.uuid7(), uuid.uuid7()
    world.items.live = {source, target}
    first = make_collection("First")
    second = make_collection("Second")
    other = make_collection("Other")
    await _put(world, first, source)
    await _put(world, second, source)
    await world.collections.add(other)

    joined = await _handler(world).handle(
        CopyItemMembershipsCommand(source_id=source, target_id=target), SYSTEM_ACTOR
    )

    assert joined == 2
    assert await _members(world, first) == {source, target}
    assert await _members(world, second) == {source, target}
    assert await _members(world, other) == set()
    assert world.uow.committed is True


async def test_smart_and_deleted_collections_are_skipped(
    world: World, make_collection: MakeCollection
) -> None:
    """A smart collection fills itself and a deleted one is not a shelf."""
    source, target = uuid.uuid7(), uuid.uuid7()
    world.items.live = {source, target}
    smart = Collection.create(
        name="Smart",
        slug=Slug("smart"),
        owner_id=uuid.uuid7(),
        definition={"type": "film"},
    )
    gone = make_collection("Gone")
    gone.soft_delete()
    await _put(world, smart, source)
    await _put(world, gone, source)

    joined = await _handler(world).handle(
        CopyItemMembershipsCommand(source_id=source, target_id=target), SYSTEM_ACTOR
    )

    assert joined == 0
    assert target not in await _members(world, smart)
    assert target not in await _members(world, gone)
    assert world.uow.committed is False


async def test_a_target_that_is_not_a_live_item_is_refused(
    world: World, make_collection: MakeCollection
) -> None:
    """Nothing is added for an unknown or deleted target."""
    source, target = uuid.uuid7(), uuid.uuid7()
    world.items.live = {source}
    shelf = make_collection()
    await _put(world, shelf, source)

    with pytest.raises(ValidationError):
        await _handler(world).handle(
            CopyItemMembershipsCommand(source_id=source, target_id=target),
            SYSTEM_ACTOR,
        )

    assert await _members(world, shelf) == {source}
