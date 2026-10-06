import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
    UninstallResult,
)
from app.modules.examples.domain.errors import PackNotInstalledError, SlugClashError
from app.modules.examples.domain.installation import (
    EntityKind,
    InstallationStatus,
    Outcome,
)
from app.modules.examples.domain.removal import KEEP_EDITED, KEEP_IN_USE, KEEP_USER_DATA
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.media.domain.media_attachment import AttachmentTarget, MediaAttachment
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from app.modules.examples.ports.pack_targets import RemoveResult
    from tests.modules.examples.conftest import MakeWorld, World


async def _install(world: World) -> None:
    await InstallExamplePack(
        world.uow, world.catalogue, world.presets, world.graph
    ).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)


async def _installed(make_world: MakeWorld) -> World:
    world = make_world()
    await _install(world)
    return world


async def _uninstall(world: World, pack_id: str = "demo") -> UninstallResult:
    return await UninstallExamplePack(world.uow, world.presets, world.graph).handle(
        UninstallExamplePackCommand(pack_id=pack_id), SYSTEM_ACTOR
    )


async def _node(world: World, name: str) -> Node:
    nodes = await world.graph_repos.nodes.list(after=None, limit=10)
    return next(n for n in nodes if n.name == name)


async def _assert_empty(world: World) -> None:
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []
    assert await world.graph_repos.node_types.list(after=None, limit=10) == []
    assert await world.graph_repos.edge_types.list(after=None, limit=10) == []
    assert await world.graph_repos.edges.list(after=None, limit=10) == []
    assert await world.preset_repos.presets.list(after=None, limit=10) == []


async def test_removes_everything_that_is_untouched(make_world: MakeWorld) -> None:
    """Untouched entities are all removed, counted, and the pack is inactive."""
    world = await _installed(make_world)

    result = await _uninstall(world)

    await _assert_empty(world)
    assert result.kept == ()
    assert (result.removed.items, result.removed.connections) == (2, 1)
    assert (
        result.removed.item_types,
        result.removed.relationship_types,
        result.removed.presets,
    ) == (2, 1, 1)
    assert await world.installations.get_active_for_pack("demo") is None


async def test_unknown_or_not_installed_pack_errors(make_world: MakeWorld) -> None:
    """Uninstalling a pack that is not installed raises."""
    world = make_world()

    with pytest.raises(PackNotInstalledError):
        await _uninstall(world)


async def test_uninstalling_twice_errors_the_second_time(
    make_world: MakeWorld,
) -> None:
    """A removed pack cannot be removed again."""
    world = await _installed(make_world)
    await _uninstall(world)

    with pytest.raises(PackNotInstalledError):
        await _uninstall(world)


async def test_reinstalling_after_removal_succeeds(make_world: MakeWorld) -> None:
    """A removed pack's slugs are free again, so it installs cleanly a second time."""
    world = await _installed(make_world)
    await _uninstall(world)

    await _install(world)

    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    assert installation.status is InstallationStatus.INSTALLED
    assert len(await world.graph_repos.node_types.list(after=None, limit=10)) == 2


async def test_an_edited_item_is_kept_and_so_are_the_types_it_needs(
    make_world: MakeWorld,
) -> None:
    """An edited item stays, and the type and preset it needs stay with it."""
    world = await _installed(make_world)
    blue = await _node(world, "Blue")
    blue.name = "Blue (my copy)"
    await world.graph_repos.nodes.save(blue)

    result = await _uninstall(world)

    reasons = {(k.kind, k.reason) for k in result.kept}
    assert (EntityKind.ITEM, KEEP_EDITED) in reasons
    assert (EntityKind.ITEM_TYPE, KEEP_IN_USE) in reasons
    assert (EntityKind.PRESET, KEEP_IN_USE) in reasons
    names = [n.name for n in await world.graph_repos.nodes.list(after=None, limit=10)]
    assert names == ["Blue (my copy)"]


async def test_no_pack_connection_is_left_dangling(make_world: MakeWorld) -> None:
    """Connections go before items, so a kept item leaves none of the pack's behind."""
    world = await _installed(make_world)
    blue = await _node(world, "Blue")
    blue.name = "Blue (my copy)"
    await world.graph_repos.nodes.save(blue)

    result = await _uninstall(world)

    assert not any(k.kind is EntityKind.CONNECTION for k in result.kept)
    assert await world.graph_repos.edges.list(after=None, limit=10) == []


async def test_an_item_with_a_users_own_connection_is_kept(
    make_world: MakeWorld,
) -> None:
    """A connection the user made to a pack item keeps that item."""
    world = await _installed(make_world)
    ada = await _node(world, "Ada")
    mine = Edge.create(source_id=ada.id, target_id=uuid.uuid7(), type="mine")
    await world.graph_repos.edges.add(mine)

    result = await _uninstall(world)

    assert any(k.label == "Ada" and k.reason == KEEP_USER_DATA for k in result.kept)
    assert any(
        k.kind is EntityKind.ITEM_TYPE and k.reason == KEEP_IN_USE for k in result.kept
    )
    assert await world.graph_repos.edges.get(mine.id) is not None
    assert [
        n.name for n in await world.graph_repos.nodes.list(after=None, limit=10)
    ] == ["Ada"]


async def test_an_item_with_an_attached_file_is_kept(make_world: MakeWorld) -> None:
    """A file attached to a pack item keeps that item."""
    world = await _installed(make_world)
    ada = await _node(world, "Ada")
    attachment = MediaAttachment.for_node(asset_id=uuid.uuid7(), node_id=ada.id)
    await world.media_repos.attachments.add(attachment)

    result = await _uninstall(world)

    assert any(k.label == "Ada" and k.reason == KEEP_USER_DATA for k in result.kept)
    assert await world.media_repos.attachments.list_for_target(
        AttachmentTarget.NODE, ada.id
    ) == [attachment]
    assert [
        n.name for n in await world.graph_repos.nodes.list(after=None, limit=10)
    ] == ["Ada"]


async def test_a_favourited_item_is_still_removed(make_world: MakeWorld) -> None:
    """Favouriting alone does not count as an edit."""
    world = await _installed(make_world)
    for node in await world.graph_repos.nodes.list(after=None, limit=10):
        node.favourite = True
        await world.graph_repos.nodes.save(node)

    result = await _uninstall(world)

    assert result.kept == ()
    await _assert_empty(world)


async def test_something_the_user_already_deleted_is_not_an_error(
    make_world: MakeWorld,
) -> None:
    """An item the user already deleted counts as removed."""
    world = await _installed(make_world)
    ada = await _node(world, "Ada")
    ada.soft_delete()
    await world.graph_repos.nodes.save(ada)

    result = await _uninstall(world)

    assert result.kept == ()
    assert result.removed.items == 2
    assert await world.installations.get_active_for_pack("demo") is None


async def test_a_preset_another_type_uses_is_kept(make_world: MakeWorld) -> None:
    """A preset the user's own type refers to is kept."""
    world = await _installed(make_world)
    preset = (await world.preset_repos.presets.list(after=None, limit=10))[0]
    mine = NodeType.create(slug="mine", label="Mine")
    mine.attributes_schema = {
        "type": "object",
        "properties": {
            "c": {"type": "string", "x-menagerist": {"list": str(preset.id)}}
        },
    }
    await world.graph_repos.node_types.add(mine)

    result = await _uninstall(world)

    assert any(
        k.kind is EntityKind.PRESET and k.reason == KEEP_IN_USE for k in result.kept
    )


async def test_kept_entities_are_no_longer_the_packs(make_world: MakeWorld) -> None:
    """A kept type's slug blocks a clean reinstall until the user deals with it."""
    world = await _installed(make_world)
    blue = await _node(world, "Blue")
    blue.name = "Mine now"
    await world.graph_repos.nodes.save(blue)
    await _uninstall(world)

    with pytest.raises(SlugClashError):
        await _install(world)


async def test_an_unfinished_installation_is_resumed(make_world: MakeWorld) -> None:
    """An installation stuck in INSTALLING is still removed cleanly."""
    world = await _installed(make_world)
    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    installation.status = InstallationStatus.INSTALLING

    result = await _uninstall(world)

    assert result.kept == ()
    await _assert_empty(world)
    assert await world.installations.get_active_for_pack("demo") is None


async def test_a_failure_during_removal_leaves_the_installation_resumable(
    make_world: MakeWorld,
) -> None:
    """A target failure propagates; nothing is marked removed, and a retry finishes."""
    world = await _installed(make_world)
    original = world.graph.remove

    async def explode(kind: EntityKind, entity_id: uuid.UUID) -> RemoveResult:
        if kind is EntityKind.ITEM:
            raise RuntimeError("boom")
        return await original(kind, entity_id)

    world.graph.remove = explode  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="boom"):
        await _uninstall(world)

    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    assert installation.status is not InstallationStatus.REMOVED
    assert {r.kind for r in installation.owned()} >= {
        EntityKind.ITEM,
        EntityKind.ITEM_TYPE,
        EntityKind.RELATIONSHIP_TYPE,
        EntityKind.PRESET,
    }
    assert all(
        r.outcome is Outcome.REMOVED
        for r in installation.entities
        if r.kind is EntityKind.CONNECTION
    )

    world.graph.remove = original  # type: ignore[method-assign]
    result = await _uninstall(world)

    assert result.kept == ()
    assert (result.removed.connections, result.removed.items) == (1, 2)
    assert (
        result.removed.item_types,
        result.removed.relationship_types,
        result.removed.presets,
    ) == (2, 1, 1)
    await _assert_empty(world)


async def test_a_users_own_item_of_a_pack_type_keeps_that_type(
    make_world: MakeWorld,
) -> None:
    """A type the user's own item uses stays, and so does the item."""
    world = await _installed(make_world)
    mine = Node.create(name="My record", type="demo-record")
    await world.graph_repos.nodes.add(mine)

    result = await _uninstall(world)

    assert any(
        k.kind is EntityKind.ITEM_TYPE
        and k.label == "Record"
        and k.reason == KEEP_IN_USE
        for k in result.kept
    )
    remaining = await world.graph_repos.nodes.list(after=None, limit=10)
    assert [n.name for n in remaining] == ["My record"]
    assert remaining[0].type == "demo-record"


async def test_a_users_connection_of_the_pack_relationship_type_keeps_it(
    make_world: MakeWorld,
) -> None:
    """A relationship type the user's own connection uses stays."""
    world = await _installed(make_world)
    mine = Edge.create(
        source_id=uuid.uuid7(), target_id=uuid.uuid7(), type="demo-signed-by"
    )
    await world.graph_repos.edges.add(mine)

    result = await _uninstall(world)

    assert any(
        k.kind is EntityKind.RELATIONSHIP_TYPE and k.reason == KEEP_IN_USE
        for k in result.kept
    )
    assert await world.graph_repos.edges.get(mine.id) is not None
    kept_types = await world.graph_repos.edge_types.list(after=None, limit=10)
    assert [str(t.slug) for t in kept_types] == ["demo-signed-by"]
