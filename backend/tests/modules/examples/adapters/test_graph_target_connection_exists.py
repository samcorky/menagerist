"""`GraphPackTarget.connection_exists`."""

from typing import TYPE_CHECKING

from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.paging import PageRequest

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld


async def test_connection_exists_looks_at_type_and_direction(
    make_world: MakeWorld,
) -> None:
    """Only a live connection of the same type in the same direction counts."""
    world = make_world()
    await InstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id="demo"), world.actor)
    [edge] = (
        await world.graph_repos.edges.list(
            scope=ContentFilter.everyone(), page=PageRequest(limit=10)
        )
    ).items

    assert await world.graph.connection_exists(
        edge.source_id, edge.target_id, edge.type
    )
    assert not await world.graph.connection_exists(
        edge.target_id, edge.source_id, edge.type
    )
    assert not await world.graph.connection_exists(
        edge.source_id, edge.target_id, "some-other-type"
    )
