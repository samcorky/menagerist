"""The exact, uncapped item count of a collection."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.collections.application.count_collection_items import (
    CountCollectionItems,
    CountCollectionItemsQuery,
)
from app.modules.collections.application.get_collection import ITEM_COUNT_CAP
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from tests.modules.collections.conftest import World

ACTOR = Actor(id=uuid.uuid7())
OTHER = Actor(id=uuid.uuid7())
DEFINITION: dict[str, Any] = {"v": 1, "where": None}


def _count(world: World) -> CountCollectionItems:
    repos = CollectionsRepos(
        collections=world.collections, memberships=world.memberships
    )
    return CountCollectionItems(repos, InMemoryAccessGuard(), world.items)


async def test_smart_collection_count_is_not_capped(world: World) -> None:
    """Above the summary cap the exact figure comes back."""
    shelf = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=ACTOR.id, definition=DEFINITION
    )
    await world.collections.add(shelf)
    world.items.live = {uuid.uuid7() for _ in range(ITEM_COUNT_CAP + 5)}

    count = await _count(world).handle(
        CountCollectionItemsQuery(collection_id=shelf.id), ACTOR
    )

    assert count == ITEM_COUNT_CAP + 5


async def test_manual_collection_counts_its_live_members(world: World) -> None:
    """Members that are no longer live items are not counted."""
    shelf = Collection.create(name="Shelf", slug=Slug("shelf"), owner_id=ACTOR.id)
    await world.collections.add(shelf)
    live, gone = uuid.uuid7(), uuid.uuid7()
    world.items.live = {live}
    for item_id in (live, gone):
        await world.memberships.add(
            Membership(
                collection_id=shelf.id, item_id=item_id, added_at=datetime.now(UTC)
            )
        )

    count = await _count(world).handle(
        CountCollectionItemsQuery(collection_id=shelf.id), ACTOR
    )

    assert count == 1


@pytest.mark.parametrize("known", [True, False])
async def test_another_owners_or_missing_collection_is_not_found(
    world: World, known: bool
) -> None:
    """Both look the same, and no count is revealed."""
    shelf = Collection.create(
        name="Smart", slug=Slug("smart"), owner_id=ACTOR.id, definition=DEFINITION
    )
    await world.collections.add(shelf)
    world.items.live = {uuid.uuid7()}
    target = shelf.id if known else uuid.uuid7()

    with pytest.raises(CollectionNotFoundError):
        await _count(world).handle(
            CountCollectionItemsQuery(collection_id=target), OTHER
        )
