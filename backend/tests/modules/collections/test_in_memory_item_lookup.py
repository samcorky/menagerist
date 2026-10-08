import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.modules.collections.conftest import World


async def test_live_ids_returns_only_live_requested_ids(world: World) -> None:
    """Only requested ids marked live come back; the live set is adjustable."""
    live, other, unknown = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    world.items.live = {live, other}
    assert await world.items.live_ids([live, unknown]) == {live}
    world.items.live.discard(live)
    assert await world.items.live_ids([live, unknown]) == set()
    assert await world.items.live_ids([]) == set()
