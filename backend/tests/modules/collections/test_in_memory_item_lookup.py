import uuid
from typing import TYPE_CHECKING

from app.shared_kernel.access_scope import AccessScope

if TYPE_CHECKING:
    from tests.modules.collections.conftest import World

ALL = AccessScope.everyone()


async def test_live_ids_returns_only_live_requested_ids(world: World) -> None:
    """Only requested ids marked live come back; the live set is adjustable."""
    live, other, unknown = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    world.items.live = {live, other}
    assert await world.items.live_ids([live, unknown], ALL) == {live}
    world.items.live.discard(live)
    assert await world.items.live_ids([live, unknown], ALL) == set()
    assert await world.items.live_ids([], ALL) == set()


async def test_owned_items_are_visible_only_inside_their_owners_scope(
    world: World,
) -> None:
    """An owned item is returned for its owner and everyone(), not for others."""
    owner, other, item = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    world.items.add_owned(item, owner)

    assert await world.items.live_ids([item], AccessScope.of(owner)) == {item}
    assert await world.items.live_ids([item], ALL) == {item}
    assert await world.items.live_ids([item], AccessScope.of(other)) == set()
