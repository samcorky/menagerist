"""The shipped add-on packs, `games-extras` and `soundtracks`, in the real catalogue."""

from typing import TYPE_CHECKING

import pytest

from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
    InstallResult,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
    UninstallResult,
)
from app.modules.examples.domain.errors import (
    RequiredByInstalledPackError,
    RequirementsNotMetError,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, World

_CATALOGUE = FilePackCatalogue()


def _world(make_world: MakeWorld) -> World:
    """An empty world; the use cases below read the shipped packs."""
    return make_world()


async def _install(world: World, pack_id: str) -> InstallResult:
    return await InstallExamplePack(
        world.uow,
        _CATALOGUE,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id=pack_id), SYSTEM_ACTOR)


async def _uninstall(world: World, pack_id: str) -> UninstallResult:
    return await UninstallExamplePack(
        world.uow,
        _CATALOGUE,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id=pack_id), SYSTEM_ACTOR)


async def _edges(world: World) -> set[tuple[str, str, str]]:
    nodes = {
        n.id: n.name for n in await world.graph_repos.nodes.list(after=None, limit=500)
    }
    return {
        (nodes[e.source_id], nodes[e.target_id], e.type)
        for e in await world.graph_repos.edges.list(after=None, limit=500)
    }


async def _live(world: World) -> int:
    repos = (
        world.graph_repos.node_types,
        world.graph_repos.nodes,
        world.graph_repos.edge_types,
        world.graph_repos.edges,
        world.preset_repos.presets,
    )
    return sum([len(await r.list(after=None, limit=500)) for r in repos]) + len(
        world.collections.collections
    )


async def test_both_add_ons_are_listed_after_the_base_packs() -> None:
    """They parse and validate in the real catalogue, in index order."""
    packs = await _CATALOGUE.list_packs()

    ids = [p.id for p in packs]
    assert ids[-2:] == ["games-extras", "soundtracks"]
    by_id = {p.id: p for p in packs}
    assert by_id["games-extras"].requires == ("games",)
    assert by_id["soundtracks"].requires == ("music", "movies")
    names = [p.name for p in packs]
    assert "Extra board games" in names
    assert "Film soundtracks" in names
    for add_on in ("games-extras", "soundtracks"):
        for other in packs:
            assert other.id == add_on or not by_id[add_on].name.startswith(other.name)


async def test_games_extras_defines_no_types_of_its_own() -> None:
    """It only uses the Board games types and publishers."""
    pack = await _CATALOGUE.get("games-extras")

    assert pack is not None
    assert (pack.item_types, pack.relationship_types) == ((), ())
    assert len(pack.items) == 5
    assert all(i.name[0].isascii() and i.name[0].isalnum() for i in pack.items)
    assert all(i.type_ref == "games:game" for i in pack.items)


async def test_games_extras_is_refused_without_board_games(
    make_world: MakeWorld,
) -> None:
    """The refusal names the missing pack and nothing is created."""
    world = _world(make_world)

    with pytest.raises(RequirementsNotMetError, match=r"Add Board games first\."):
        await _install(world, "games-extras")

    assert await _live(world) == 0


async def test_games_extras_connects_to_the_base_and_comes_out_cleanly(
    make_world: MakeWorld,
) -> None:
    """New games link to base publishers; the expansion links to a base game."""
    world = _world(make_world)
    await _install(world, "games")
    base = await _live(world)
    base_covers = len(world.covers.create_calls)

    result = await _install(world, "games-extras")

    edges = await _edges(world)
    assert (
        "Lantern Harbour: The Night Fair",
        "Lantern Harbour",
        "games-expansion-of",
    ) in edges
    assert ("Quillfeather Quarry", "Marrow Lane Press", "games-published-by") in edges
    assert (result.created.items, result.created.collections) == (5, 1)
    assert (result.created.item_types, result.created.relationship_types) == (0, 0)
    assert len(world.covers.create_calls) == 5 + base_covers
    with pytest.raises(
        RequiredByInstalledPackError, match=r"Remove Extra board games first\."
    ):
        await _uninstall(world, "games")

    removed = await _uninstall(world, "games-extras")

    assert removed.kept == ()
    assert await _live(world) == base
    assert (await _uninstall(world, "games")).kept == ()
    assert await _live(world) == 0


async def test_soundtracks_needs_both_music_and_movies(make_world: MakeWorld) -> None:
    """With only one of the two installed it is refused, naming the other."""
    world = _world(make_world)
    await _install(world, "music")
    music_only = await _live(world)

    with pytest.raises(RequirementsNotMetError, match=r"Add Movies first\."):
        await _install(world, "soundtracks")

    assert await _live(world) == music_only


async def test_soundtracks_links_records_to_films_and_comes_out_cleanly(
    make_world: MakeWorld,
) -> None:
    """Four records are the soundtracks of four films; removal leaves nothing."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    base = await _live(world)

    result = await _install(world, "soundtracks")

    assert (result.created.items, result.created.connections) == (0, 4)
    assert result.created.relationship_types == 1
    edges = await _edges(world)
    assert ("Night Drive", "Cold Harbour", "soundtracks-soundtrack-of") in edges
    assert ("Thirteen Bells", "Marmalade", "soundtracks-soundtrack-of") in edges
    for base_id in ("music", "movies"):
        with pytest.raises(
            RequiredByInstalledPackError, match=r"Remove Film soundtracks first\."
        ):
            await _uninstall(world, base_id)

    assert (await _uninstall(world, "soundtracks")).kept == ()
    assert await _live(world) == base
    for base_id in ("music", "movies"):
        assert (await _uninstall(world, base_id)).kept == ()
    assert await _live(world) == 0
