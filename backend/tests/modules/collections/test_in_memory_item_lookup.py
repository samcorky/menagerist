import uuid
from typing import TYPE_CHECKING

from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from tests.modules.collections.conftest import World

ALL = ContentFilter.everyone()


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

    assert await world.items.live_ids([item], ContentFilter.of(owner)) == {item}
    assert await world.items.live_ids([item], ALL) == {item}
    assert await world.items.live_ids([item], ContentFilter.of(other)) == set()


async def test_count_matching_without_a_cap_is_exact(world: World) -> None:
    """`cap=None` counts every item inside the scope."""
    world.items.live = {uuid.uuid7() for _ in range(5)}
    assert await world.items.count_matching({}, ALL, cap=None) == (5, False)
    assert await world.items.count_matching({}, ALL, cap=3) == (3, True)
