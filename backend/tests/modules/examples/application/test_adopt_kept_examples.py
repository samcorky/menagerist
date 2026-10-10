"""Reinstalling a pack takes back what its earlier removal kept."""

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

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
from app.modules.examples.domain.errors import InstallFailedError, SlugClashError
from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import PackCollection
from app.modules.examples.domain.removal import KEEP_EDITED
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node
    from tests.modules.examples.conftest import MakeWorld, SamplePack, World


async def _install(world: World) -> InstallResult:
    return await InstallExamplePack(
        world.uow,
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)


async def _uninstall(world: World) -> UninstallResult:
    return await UninstallExamplePack(
        world.uow,
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)


async def _node(world: World, name: str) -> Node:
    nodes = await world.graph_repos.nodes.list(after=None, limit=10)
    return next(n for n in nodes if n.name == name)


async def _names(world: World) -> list[str]:
    nodes = await world.graph_repos.nodes.list(after=None, limit=10)
    return sorted(n.name for n in nodes)


async def _slugs(world: World) -> list[str]:
    types = await world.graph_repos.node_types.list(after=None, limit=10)
    return sorted(str(t.slug) for t in types)


async def _kept_world(make_world: MakeWorld) -> World:
    """Install, rename Blue, remove: Blue and its type are kept."""
    world = make_world()
    await _install(world)
    blue = await _node(world, "Blue")
    blue.name = "Mine now"
    await world.graph_repos.nodes.save(blue)
    kept = await _uninstall(world)
    assert {(k.kind, k.label) for k in kept.kept} >= {
        (EntityKind.ITEM, "Blue"),
        (EntityKind.ITEM_TYPE, "Record"),
    }
    return world


async def test_reinstall_adopts_the_kept_type_and_item(make_world: MakeWorld) -> None:
    """The kept item and its type are reused: no clash, no duplicate."""
    world = await _kept_world(make_world)
    blue_id = (await _node(world, "Mine now")).id

    result = await _install(world)

    assert (result.adopted.item_types, result.adopted.items) == (1, 1)
    assert result.adopted.relationship_types == 0
    assert result.adopted.connections == 0
    assert (result.created.item_types, result.created.items) == (1, 1)
    assert (result.created.relationship_types, result.created.connections) == (1, 1)
    assert await _names(world) == ["Ada", "Mine now"]
    assert await _slugs(world) == ["demo-person", "demo-record"]
    assert (await _node(world, "Mine now")).id == blue_id
    assert world.uow.committed is True


async def test_adopted_entities_are_recorded_as_owned_by_the_new_install(
    make_world: MakeWorld,
) -> None:
    """The new installation owns the adopted item, ready for the next removal."""
    world = await _kept_world(make_world)
    blue_id = (await _node(world, "Mine now")).id

    await _install(world)

    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    assert blue_id in {r.entity_id for r in installation.owned(EntityKind.ITEM)}
    assert len(installation.owned()) == 6  # preset 0, blue and the type adopted


async def test_the_original_hash_is_kept_so_a_second_removal_keeps_it_again(
    make_world: MakeWorld,
) -> None:
    """Adoption never reduces protection: the edited item is still an edit."""
    world = await _kept_world(make_world)
    await _install(world)

    again = await _uninstall(world)

    assert {(k.kind, k.label, k.reason) for k in again.kept} >= {
        (EntityKind.ITEM, "Blue", KEEP_EDITED)
    }
    assert await _names(world) == ["Mine now"]
    third = await _install(world)  # two rounds in a row still adopt
    assert (third.adopted.items, third.adopted.item_types) == (1, 1)
    assert await _names(world) == ["Ada", "Mine now"]


async def test_a_later_removal_supersedes_an_older_kept_record(
    make_world: MakeWorld,
) -> None:
    """Once the user reverts the edit and the item is removed, it is created anew."""
    world = await _kept_world(make_world)
    await _install(world)
    blue = await _node(world, "Mine now")
    blue.name = "Blue"  # back to what the pack wrote
    await world.graph_repos.nodes.save(blue)
    await _uninstall(world)
    assert await _names(world) == []

    result = await _install(world)

    assert result.adopted.items == 0
    assert result.created.items == 2


async def test_a_type_whose_slug_the_user_changed_is_not_adopted(
    make_world: MakeWorld,
) -> None:
    """A renamed kept type is the user's; the pack gets a fresh one."""
    world = await _kept_world(make_world)
    types = await world.graph_repos.node_types.list(after=None, limit=10)
    mine = types[0]
    mine.slug = "my-records"  # type: ignore[assignment]
    await world.graph_repos.node_types.save(mine)

    result = await _install(world)

    assert result.adopted.item_types == 0
    assert result.created.item_types == 2
    assert await _slugs(world) == ["demo-person", "demo-record", "my-records"]


async def test_an_entity_that_is_gone_is_created_fresh(make_world: MakeWorld) -> None:
    """A kept item the user has since deleted is simply created again."""
    world = await _kept_world(make_world)
    await world.graph.remove(EntityKind.ITEM, (await _node(world, "Mine now")).id)

    result = await _install(world)

    assert (result.adopted.items, result.adopted.item_types) == (0, 1)
    assert result.created.items == 2
    assert await _names(world) == ["Ada", "Blue"]


async def test_a_clash_with_something_that_is_not_a_kept_example_still_conflicts(
    make_world: MakeWorld,
) -> None:
    """The user's own type with a needed slug is never silently merged."""
    world = await _kept_world(make_world)
    await world.graph_repos.node_types.add(
        NodeType.create(slug="demo-person", label="Mine")
    )

    with pytest.raises(SlugClashError, match="demo-person"):
        await _install(world)

    assert await world.installations.get_active_for_pack("demo") is None


async def test_a_relationship_type_clash_still_conflicts(
    make_world: MakeWorld,
) -> None:
    """The same holds for relationship types."""
    world = await _kept_world(make_world)
    await world.graph_repos.edge_types.add(
        EdgeType.create(slug="demo-signed-by", label="Mine")
    )

    with pytest.raises(SlugClashError, match="demo-signed-by"):
        await _install(world)


async def test_a_failed_install_keeps_the_edited_things_it_adopted(
    make_world: MakeWorld,
) -> None:
    """Rollback only removes what is unchanged; adopted edits stay."""
    world = await _kept_world(make_world)

    async def boom(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise RuntimeError("boom")

    world.graph.create_connection = boom  # type: ignore[method-assign]

    with pytest.raises(InstallFailedError, match="you had changed were kept"):
        await _install(world)

    assert await _names(world) == ["Mine now"]
    assert "demo-record" in await _slugs(world)
    assert await world.installations.get_active_for_pack("demo") is None


async def _connection_kept_world(make_world: MakeWorld) -> World:
    """Install, edit the connection, remove: everything is kept."""
    world = make_world()
    await _install(world)
    edge = (await world.graph_repos.edges.list(after=None, limit=10))[0]
    edge.attributes = {"note": "mine"}
    await world.graph_repos.edges.save(edge)
    kept = await _uninstall(world)
    assert EntityKind.CONNECTION in {k.kind for k in kept.kept}
    return world


async def test_connections_are_adopted_when_they_still_join_the_same_items(
    make_world: MakeWorld,
) -> None:
    """A kept connection is reused, so nothing is created twice."""
    world = await _connection_kept_world(make_world)

    result = await _install(world)

    assert (result.adopted.connections, result.adopted.items) == (1, 2)
    assert (result.adopted.item_types, result.adopted.relationship_types) == (2, 1)
    assert result.created.connections == 0
    assert len(await world.graph_repos.edges.list(after=None, limit=10)) == 1


async def test_a_connection_to_a_replaced_item_is_created_fresh(
    make_world: MakeWorld,
) -> None:
    """If an end of the kept connection was recreated, the old edge is not reused."""
    world = await _connection_kept_world(make_world)
    await world.graph.remove(EntityKind.ITEM, (await _node(world, "Ada")).id)

    result = await _install(world)

    assert (result.adopted.connections, result.created.connections) == (0, 1)
    assert (result.adopted.items, result.created.items) == (1, 1)


async def test_collections_are_adopted_as_the_user_has_them(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A kept collection is reused untouched; an untouched one is created again."""
    all_ = PackCollection(ref="all", name="Everything", item_refs=("ada", "blue"))
    solo = PackCollection(ref="solo", name="Just Blue", item_refs=("blue",))
    world = make_world(replace(sample_pack(), collections=(all_, solo)))
    await _install(world)
    everything = next(
        c for c in world.collections.collections.values() if c.name == "Everything"
    )
    everything.name = "My shelf"
    kept_members = list(everything.members)
    await _uninstall(world)

    result = await _install(world)

    assert (result.adopted.collections, result.created.collections) == (1, 1)
    shelf = world.collections.collections[everything.id]
    assert (shelf.name, shelf.members) == ("My shelf", kept_members)
    assert sorted(c.name for c in world.collections.collections.values()) == [
        "Just Blue",
        "My shelf",
    ]
    assert len(world.collections.create_calls) == 3  # two first time, one now


async def test_a_pack_with_nothing_kept_adopts_nothing(make_world: MakeWorld) -> None:
    """A plain reinstall after a clean removal is unchanged."""
    world = make_world()
    await _install(world)
    await _uninstall(world)

    result = await _install(world)

    assert sum(vars(result.adopted).values()) == 0
    assert result.created.items == 2
