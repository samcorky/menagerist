"""What each shipped pack smart collection matches once the pack is installed.

The names are asserted exactly, so editing a pack's data in a way that changes the
answer is noticed.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.bridges.example_targets import (
    CollectionPackTarget,
    build_in_memory_collections_repos,
    in_memory_collection_stores,
)
from app.modules.collections.domain.collection import CollectionKind
from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
)
from app.modules.examples.domain.pack import PackConnection
from app.modules.graph.application.prepare_query import prepare_query
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.collections.ports.unit_of_work import CollectionsRepos
    from tests.modules.examples.conftest import MakeWorld, World

_EVERYONE = ContentFilter.everyone()
_SMART = [
    ("games", "Still to try"),
    ("movies", "No poster yet"),
    ("parts", "Running low"),
]


class Rig:
    """A world whose collections are the real target over in-memory storage."""

    def __init__(self, world: World, repos: CollectionsRepos) -> None:
        self.world = world
        self.repos = repos
        self.target = CollectionPackTarget(
            in_memory_collection_stores(repos, world.graph_repos), world.actor
        )

    async def install(self, pack_id: str) -> None:
        """Install the pack."""
        await InstallExamplePack(
            self.world.uow,
            InMemoryAccessGuard(),
            self.world.catalogue,
            self.world.presets,
            self.world.graph,
            self.target,
            self.world.covers,
        ).handle(InstallExamplePackCommand(pack_id=pack_id), self.world.actor)

    async def uninstall(self, pack_id: str) -> None:
        """Remove the pack."""
        await UninstallExamplePack(
            self.world.uow,
            InMemoryAccessGuard(),
            self.world.catalogue,
            self.world.presets,
            self.world.graph,
            self.target,
            self.world.covers,
        ).handle(UninstallExamplePackCommand(pack_id=pack_id), self.world.actor)

    async def collections(self) -> dict[str, tuple[CollectionKind, dict[str, object]]]:
        """Return kind and definition by collection name."""
        found = await self.repos.collections.list(
            scope=_EVERYONE, after=None, limit=100
        )
        return {c.name: (c.kind, c.definition or {}) for c in found}

    async def matches(self, name: str) -> list[str]:
        """Names of the items the smart collection `name` matches, sorted."""
        kind, definition = (await self.collections())[name]
        assert kind is CollectionKind.DYNAMIC
        resolved, warnings = await prepare_query(
            self.world.graph_repos,
            definition,
            datetime.now(UTC).date(),
            scope=_EVERYONE,
        )
        assert warnings == []
        hits = await self.world.graph_repos.nodes.search(
            scope=_EVERYONE, resolved=resolved, after=None, limit=500
        )
        return sorted(hit.node.name for hit in hits)


async def _rig(make_world: MakeWorld, *pack_ids: str) -> Rig:
    catalogue = FilePackCatalogue()
    packs = []
    for pack_id in pack_ids:
        pack = await catalogue.get(pack_id)
        assert pack is not None
        packs.append(pack)
    return Rig(make_world(*packs), build_in_memory_collections_repos())


async def test_still_to_try_is_owned_games_never_played(
    make_world: MakeWorld,
) -> None:
    """Owned (a condition is recorded; the wishlist has none) and never played.

    This is the pack's former hand-built list.
    """
    rig = await _rig(make_world, "games")
    await rig.install("games")

    assert await rig.matches("Still to try") == [
        "Cobbled Streets: The Canal Expansion",
        "Slow Parcel Panic",
        "Thornfield Heist",
    ]


async def test_still_to_try_follows_the_data(make_world: MakeWorld) -> None:
    """Playing a game takes it off the list; it is a rule, not a list."""
    rig = await _rig(make_world, "games")
    await rig.install("games")
    items = {
        n.name: n.id
        for n in await rig.world.graph_repos.nodes.list(
            scope=_EVERYONE, after=None, limit=100
        )
    }
    night = items["Autumn game night"]
    await rig.world.graph.create_connection(
        PackConnection(source_ref="g", target_ref="n", type_ref="played-at"),
        source_id=items["Thornfield Heist"],
        target_id=night,
        type_slug="games-played-at",
    )

    assert await rig.matches("Still to try") == [
        "Cobbled Streets: The Canal Expansion",
        "Slow Parcel Panic",
    ]


async def test_films_without_a_poster_are_found_by_the_missing_connection(
    make_world: MakeWorld,
) -> None:
    """A poster is `memorabilia-for` a film, so the film is the target end."""
    rig = await _rig(make_world, "movies")
    await rig.install("movies")

    assert await rig.matches("No poster yet") == [
        "Marmalade",
        "The Night Bus Sessions",
    ]


async def test_running_low_compares_each_part_with_its_own_reorder_level(
    make_world: MakeWorld,
) -> None:
    """Stock at or under `reorder_at` (a `ref`), so the solder reel (1 of 1) counts.

    The old hand-built list also held the 470 uF capacitor (12 in stock, reorder
    at 10), which is above its level and so no longer matches.
    """
    rig = await _rig(make_world, "parts")
    await rig.install("parts")

    assert await rig.matches("Running low") == [
        "10-turn trimmer potentiometer",
        "LM317 voltage regulator",
        "Solder wire, 0.8 mm, 100 g reel",
    ]


@pytest.mark.parametrize(("pack_id", "name"), _SMART)
async def test_a_pack_smart_collection_goes_with_the_pack_and_comes_back(
    make_world: MakeWorld, pack_id: str, name: str
) -> None:
    """Uninstall removes it; reinstalling gives the same answer."""
    rig = await _rig(make_world, pack_id)
    await rig.install(pack_id)
    before = await rig.matches(name)

    await rig.uninstall(pack_id)
    assert name not in await rig.collections()

    await rig.install(pack_id)
    assert await rig.matches(name) == before
    assert before != []


async def test_the_other_games_collections_stay_manual(
    make_world: MakeWorld,
) -> None:
    """Only the collection with an honest rule in the pack's data converted."""
    rig = await _rig(make_world, "games")
    await rig.install("games")

    kinds = {name: kind for name, (kind, _) in (await rig.collections()).items()}

    assert kinds == {
        "Wishlist": CollectionKind.MANUAL,
        "Games for two": CollectionKind.MANUAL,
        "Family game night": CollectionKind.MANUAL,
        "Still to try": CollectionKind.DYNAMIC,
    }
