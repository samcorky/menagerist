from typing import TYPE_CHECKING

from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.application.list_example_packs import (
    ListExamplePacks,
    ListExamplePacksQuery,
)
from app.modules.examples.domain.installation import Installation
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, SamplePack


async def test_lists_each_pack_with_its_active_installation(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Each pack carries its active installation; removed ones do not count."""
    world = make_world(sample_pack("one"), sample_pack("two"))
    installed = Installation.start("two")
    installed.mark_installed()
    await world.installations.add(installed)
    removed = Installation.start("one")
    removed.mark_removed()
    await world.installations.add(removed)

    result = await ListExamplePacks(
        ExampleRepos(installations=world.installations), world.catalogue
    ).handle(ListExamplePacksQuery(), SYSTEM_ACTOR)

    by_id = {s.summary.id: s for s in result}
    assert by_id["one"].installation is None
    assert by_id["two"].installation is installed
    assert [s.summary.id for s in result] == ["one", "two"]


async def test_lists_nothing_for_an_empty_catalogue() -> None:
    """An empty catalogue yields an empty list."""
    result = await ListExamplePacks(
        ExampleRepos(installations=InMemoryInstallationRepository()),
        InMemoryPackCatalogue(),
    ).handle(ListExamplePacksQuery(), SYSTEM_ACTOR)
    assert result == []
