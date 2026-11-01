"""Links: they appear when the second pack arrives, in either order."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
    InstallResult,
    installation_counts,
)
from app.modules.examples.application.pack_links import apply_links
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
    UninstallResult,
)
from app.modules.examples.domain.installation import EntityKind, Installation, Outcome
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackItem,
    PackItemType,
    PackLink,
    PackRelationshipType,
)
from app.modules.examples.domain.removal import KEEP_EDITED
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, World

USER_B = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))


def _side(pack_id: str, *links: PackLink) -> ExamplePack:
    title = pack_id.title()
    return ExamplePack(
        id=pack_id,
        relationship_types=(
            PackRelationshipType(
                ref="tie", slug=f"{pack_id}-tie", label="Tie", reverse_label="Tied"
            ),
        ),
        item_types=(
            PackItemType(ref="thing", slug=f"{pack_id}-thing", label=f"{title} thing"),
        ),
        items=(
            PackItem(ref="a", type_ref="thing", name=f"{title} A"),
            PackItem(ref="b", type_ref="thing", name=f"{title} B"),
        ),
        links=links,
    )


def _world(make_world: MakeWorld) -> World:
    """`music` declares one link to `movies`; `movies` declares none."""
    link = PackLink(
        with_pack="movies", source_ref="a", target_ref="movies:a", type_ref="tie"
    )
    return make_world(_side("movies"), _side("music", link))


async def _install(world: World, pack_id: str) -> InstallResult:
    return await InstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id=pack_id), world.actor)


async def _pairs(world: World) -> set[tuple[str, str]]:
    names = {
        n.id: n.name
        for n in await world.graph_repos.nodes.list(
            scope=ContentFilter.everyone(), after=None, limit=50
        )
    }
    edges = await world.graph_repos.edges.list(
        after=None, limit=50, scope=ContentFilter.everyone()
    )
    return {(names[e.source_id], names[e.target_id]) for e in edges}


async def _installation(world: World, pack_id: str) -> Installation:
    found = await world.installations.get_active_for_pack(
        pack_id, scope=ContentFilter.everyone()
    )
    assert found is not None
    return found


@pytest.mark.parametrize(
    ("first", "second"), [("music", "movies"), ("movies", "music")]
)
async def test_links_appear_when_the_second_pack_arrives(
    make_world: MakeWorld, first: str, second: str
) -> None:
    """Either order gives the same connection, recorded under the declaring pack."""
    world = _world(make_world)

    await _install(world, first)
    assert await _pairs(world) == set()
    result = await _install(world, second)

    assert await _pairs(world) == {("Music A", "Movies A")}
    assert result.linked == 1
    assert result.created.connections == 0  # the pack's own content only
    [record] = (await _installation(world, "music")).owned(EntityKind.CONNECTION)
    assert record.ref == "link:movies:0"
    assert record.label == "Music A to Movies A"
    assert (await _installation(world, "movies")).owned(EntityKind.CONNECTION) == []


async def test_a_pack_with_no_partner_installed_links_nothing(
    make_world: MakeWorld,
) -> None:
    """Links wait for the other pack."""
    world = _world(make_world)

    result = await _install(world, "music")

    assert result.linked == 0
    assert await _pairs(world) == set()


async def test_a_deleted_endpoint_skips_the_link_quietly(
    make_world: MakeWorld,
) -> None:
    """The person deleted Movies A before Music arrived: no link, no error."""
    world = _world(make_world)
    await _install(world, "movies")
    movies_a = next(
        n
        for n in await world.graph_repos.nodes.list(
            scope=ContentFilter.everyone(), after=None, limit=50
        )
        if n.name == "Movies A"
    )
    movies_a.soft_delete()
    await world.graph_repos.nodes.save(movies_a)

    result = await _install(world, "music")

    assert result.linked == 0
    assert (await _installation(world, "music")).status.value == "installed"
    assert await _pairs(world) == set()


async def test_a_failing_link_does_not_fail_the_install(
    make_world: MakeWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pack is installed; the link is logged and skipped."""
    world = _world(make_world)
    await _install(world, "music")

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("link boom")

    monkeypatch.setattr(world.graph, "create_connection", boom)

    result = await _install(world, "movies")

    assert result.linked == 0
    assert (await _installation(world, "movies")).status.value == "installed"
    assert await _pairs(world) == set()


async def test_another_persons_installations_are_left_alone(
    make_world: MakeWorld,
) -> None:
    """One person installing a pack never links into someone else's."""
    world = _world(make_world)
    await _install(world, "music")

    other = world.as_actor(USER_B)
    result = await _install(other, "movies")

    assert result.linked == 0
    assert await _pairs(world) == set()
    music = await _installation(world, "music")
    assert all(r.outcome is Outcome.OWNED for r in music.entities)


async def _uninstall(world: World, pack_id: str) -> UninstallResult:
    return await UninstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id=pack_id), world.actor)


async def test_removing_the_other_pack_removes_the_link(make_world: MakeWorld) -> None:
    """Removal is not refused, and the declaring pack stays installed."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")

    await _uninstall(world, "movies")

    assert await _pairs(world) == set()
    music = await _installation(world, "music")
    assert music.owned(EntityKind.CONNECTION) == []


async def test_the_link_returns_exactly_once_when_the_pack_is_added_back(
    make_world: MakeWorld,
) -> None:
    """Remove and re-add: one connection, not two."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    await _uninstall(world, "movies")

    again = await _install(world, "movies")

    assert again.linked == 1
    assert await _pairs(world) == {("Music A", "Movies A")}


async def test_removing_the_declaring_pack_removes_the_link(
    make_world: MakeWorld,
) -> None:
    """Its own links go with the rest of its connections."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")

    await _uninstall(world, "music")

    assert await _pairs(world) == set()
    names = {
        n.name
        for n in await world.graph_repos.nodes.list(
            scope=ContentFilter.everyone(), after=None, limit=50
        )
    }
    assert names == {"Movies A", "Movies B"}


@pytest.mark.parametrize("remove", ["movies", "music"])
async def test_an_edited_link_is_kept_and_keeps_its_item(
    make_world: MakeWorld, remove: str
) -> None:
    """Editing the link makes it the person's: it stays, and so does the item."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    [edge] = await world.graph_repos.edges.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    edge.attributes = {"note": "mine"}
    await world.graph_repos.edges.save(edge)

    removed = await _uninstall(world, remove)

    assert (EntityKind.CONNECTION, KEEP_EDITED) in {
        (k.kind, k.reason) for k in removed.kept
    }
    assert await _pairs(world) == {("Music A", "Movies A")}


async def test_a_kept_link_is_not_duplicated_when_the_pack_comes_back(
    make_world: MakeWorld,
) -> None:
    """The kept connection already satisfies the link."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    [edge] = await world.graph_repos.edges.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    edge.attributes = {"note": "mine"}
    await world.graph_repos.edges.save(edge)
    await _uninstall(world, "movies")

    again = await _install(world, "movies")

    assert again.linked == 0
    assert len(await _pairs(world)) == 1


async def test_nothing_is_refused_in_either_order(make_world: MakeWorld) -> None:
    """Links never block removal."""
    world = _world(make_world)
    await _install(world, "movies")
    await _install(world, "music")

    await _uninstall(world, "movies")
    await _uninstall(world, "music")

    assert await _pairs(world) == set()


async def test_only_links_with_the_installed_partner_are_applied(
    make_world: MakeWorld,
) -> None:
    """A pack linking with two packs links just the one that is installed."""
    to_movies = PackLink(
        with_pack="movies", source_ref="a", target_ref="movies:a", type_ref="tie"
    )
    to_games = PackLink(
        with_pack="games", source_ref="b", target_ref="games:b", type_ref="tie"
    )
    hub = _side("hub", to_movies, to_games)
    world = make_world(_side("movies"), _side("games"), hub)
    await _install(world, "movies")

    result = await _install(world, "hub")

    assert result.linked == 1
    assert await _pairs(world) == {("Hub A", "Movies A")}


async def test_applying_the_same_links_twice_makes_them_once(
    make_world: MakeWorld,
) -> None:
    """A link already recorded as owned is not made again."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    music = await world.catalogue.get("music")
    assert music is not None

    async def save(installation: Installation) -> None:
        await world.installations.save(installation)

    again = await apply_links(
        declaring_pack=music,
        declaring=await _installation(world, "music"),
        other=await _installation(world, "movies"),
        graph=world.graph,
        persist=save,
    )

    assert again == 0
    assert len(await _pairs(world)) == 1


async def test_an_item_the_installation_does_not_own_skips_the_link(
    make_world: MakeWorld,
) -> None:
    """E.g. a newer pack file names an item the installed version never made."""
    world = _world(make_world)
    await _install(world, "movies")
    movies = await _installation(world, "movies")
    movies.entities = [
        r for r in movies.entities if not (r.kind is EntityKind.ITEM and r.ref == "a")
    ]
    await world.installations.save(movies)

    result = await _install(world, "music")

    assert result.linked == 0
    assert await _pairs(world) == set()


async def test_counts_stay_true_after_the_partner_is_removed_and_added_back(
    make_world: MakeWorld,
) -> None:
    """The stale record of the removed link must not inflate the pack's counts."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    await _uninstall(world, "movies")
    await _install(world, "movies")

    music = await _installation(world, "music")

    assert installation_counts(music).connections == 1
    assert len([r for r in music.entities if r.ref == "link:movies:0"]) == 1
