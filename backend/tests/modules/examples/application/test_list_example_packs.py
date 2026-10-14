import uuid
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
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
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackItem,
    PackItemType,
    PackLink,
    PackRelationshipType,
)
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, SamplePack


USER_A = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))


async def test_lists_each_pack_with_its_active_installation(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Each pack carries its active installation; removed ones do not count."""
    world = make_world(sample_pack("one"), sample_pack("two"))
    installed = Installation.start("two", USER_A.id)
    installed.mark_installed()
    await world.installations.add(installed)
    removed = Installation.start("one", USER_A.id)
    removed.mark_removed()
    await world.installations.add(removed)

    result = await ListExamplePacks(
        ExampleRepos(installations=world.installations),
        OwnerAccessPolicy(),
        world.catalogue,
    ).handle(ListExamplePacksQuery(), world.actor)

    by_id = {s.summary.id: s for s in result}
    assert by_id["one"].installation is None
    assert by_id["two"].installation is installed
    assert [s.summary.id for s in result] == ["one", "two"]


def _linking_packs() -> tuple[ExamplePack, ExamplePack]:
    """`movies` first, then `music`, which links with it."""

    def side(pack_id: str, *links: PackLink) -> ExamplePack:
        return ExamplePack(
            id=pack_id,
            relationship_types=(
                PackRelationshipType(ref="tie", slug=f"{pack_id}-tie", label="Tie"),
            ),
            item_types=(
                PackItemType(ref="thing", slug=f"{pack_id}-thing", label="Thing"),
            ),
            items=(PackItem(ref="a", type_ref="thing", name=f"{pack_id} A"),),
            links=links,
        )

    link = PackLink(
        with_pack="movies", source_ref="a", target_ref="movies:a", type_ref="tie"
    )
    return side("movies"), side("music", link)


async def test_a_pack_lists_the_packs_it_links_with(make_world: MakeWorld) -> None:
    """`links_with` carries the other packs' names, not only their ids."""
    world = make_world(*_linking_packs())

    result = await ListExamplePacks(
        ExampleRepos(installations=world.installations),
        OwnerAccessPolicy(),
        world.catalogue,
    ).handle(ListExamplePacksQuery(), world.actor)

    by_id = {s.summary.id: s for s in result}
    assert [p.id for p in by_id["music"].links_with] == ["movies"]
    assert by_id["movies"].links_with == ()


async def test_lists_nothing_for_an_empty_catalogue() -> None:
    """An empty catalogue yields an empty list."""
    result = await ListExamplePacks(
        ExampleRepos(installations=InMemoryInstallationRepository()),
        OwnerAccessPolicy(),
        InMemoryPackCatalogue(),
    ).handle(ListExamplePacksQuery(), USER_A)
    assert result == []
