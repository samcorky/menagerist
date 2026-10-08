import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

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
from app.modules.examples.domain.errors import InstallFailedError
from app.modules.examples.domain.installation import (
    EntityKind,
    InstallationStatus,
    Outcome,
)
from app.modules.examples.domain.pack import ExamplePack, PackCollection
from app.modules.examples.domain.removal import KEEP_EDITED, KEEP_USER_DATA
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.examples.conftest import (
        FakeCollection,
        MakeWorld,
        SamplePack,
        World,
    )

_ALL = PackCollection(
    ref="all", name="Everything", description="Both", item_refs=("ada", "blue")
)
_SOLO = PackCollection(ref="solo", name="Just Blue", item_refs=("blue",))


def _pack(sample_pack: SamplePack, *collections: PackCollection) -> ExamplePack:
    return replace(sample_pack(), collections=collections or (_ALL, _SOLO))


async def _install(world: World) -> InstallResult:
    return await InstallExamplePack(
        world.uow, world.catalogue, world.presets, world.graph, world.collections
    ).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)


async def _uninstall(world: World) -> UninstallResult:
    return await UninstallExamplePack(
        world.uow, world.presets, world.graph, world.collections
    ).handle(UninstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)


async def _world(
    make_world: MakeWorld, sample_pack: SamplePack, *collections: PackCollection
) -> World:
    return make_world(_pack(sample_pack, *collections))


async def _item_id(world: World, name: str) -> uuid.UUID:
    nodes = await world.graph_repos.nodes.list(after=None, limit=10)
    return next(n.id for n in nodes if n.name == name)


def _live(world: World, name: str) -> FakeCollection:
    return next(c for c in world.collections.collections.values() if c.name == name)


async def test_install_creates_collections_with_their_members(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Each collection gets its items in pack order, and the counts include them."""
    world = await _world(make_world, sample_pack)

    result = await _install(world)

    ada, blue = await _item_id(world, "Ada"), await _item_id(world, "Blue")
    assert [(spec.ref, ids) for spec, ids in world.collections.create_calls] == [
        ("all", [ada, blue]),
        ("solo", [blue]),
    ]
    assert result.created.collections == 2
    assert result.created.items == 2
    assert _live(world, "Everything").description == "Both"
    assert _live(world, "Just Blue").description is None


async def test_install_records_each_collection_with_a_hash(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The installation holds a collection record per pack collection."""
    world = await _world(make_world, sample_pack)
    await _install(world)

    installation = await world.installations.get_active_for_pack("demo")

    assert installation is not None
    records = installation.owned(EntityKind.COLLECTION)
    assert [(r.ref, r.label) for r in records] == [
        ("all", "Everything"),
        ("solo", "Just Blue"),
    ]
    assert all(r.content_hash for r in records)
    assert installation.entities[-1].kind is EntityKind.COLLECTION  # after connections


@pytest.mark.parametrize("fail_on_call", [1, 2])
async def test_a_failing_collection_step_rolls_everything_back(
    make_world: MakeWorld, sample_pack: SamplePack, fail_on_call: int
) -> None:
    """A collection that cannot be made undoes the items, types and collections."""
    world = await _world(make_world, sample_pack)
    world.collections.fail_on_call = fail_on_call
    statuses: list[InstallationStatus] = []
    original = world.installations.save

    async def spy(installation: object) -> None:
        statuses.append(installation.status)  # type: ignore[attr-defined]
        await original(installation)  # type: ignore[arg-type]

    world.installations.save = spy  # type: ignore[method-assign]

    with pytest.raises(InstallFailedError, match="collection boom"):
        await _install(world)

    assert statuses[-1] is InstallationStatus.FAILED
    assert world.collections.collections == {}
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []
    assert await world.graph_repos.node_types.list(after=None, limit=10) == []
    assert await world.preset_repos.presets.list(after=None, limit=10) == []
    assert await world.installations.get_active_for_pack("demo") is None
    assert world.collections.events.count("collection") == fail_on_call - 1
    assert world.collections.events[0] == "connection"


async def test_a_collection_naming_a_missing_item_fails_the_install(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Defensively, an item ref that was never created fails and rolls back."""
    pack = sample_pack()
    object.__setattr__(
        pack,
        "collections",
        (PackCollection(ref="bad", name="Bad", item_refs=("ghost",)),),
    )
    world = make_world(pack)

    with pytest.raises(InstallFailedError, match="ghost"):
        await _install(world)

    assert world.collections.create_calls == []
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []


async def test_uninstall_removes_collections_before_items(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Untouched collections go first, so their members are removable."""
    world = await _world(make_world, sample_pack)
    await _install(world)

    result = await _uninstall(world)

    assert result.kept == ()
    assert result.removed.collections == 2
    assert world.collections.collections == {}
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []
    assert world.collections.events == [
        "connection",
        "collection",
        "collection",
        "item",
        "item",
        "item_type",
        "item_type",
        "relationship_type",
    ]


@pytest.mark.parametrize(
    ("edit", "kept_items"),
    [
        ("rename", {"Ada", "Blue"}),
        ("describe", {"Ada", "Blue"}),
        ("add_member", {"Ada", "Blue"}),
        ("remove_member", {"Blue"}),
    ],
)
async def test_an_edited_collection_is_kept_with_its_remaining_members(
    make_world: MakeWorld,
    sample_pack: SamplePack,
    edit: str,
    kept_items: set[str],
) -> None:
    """Any edit keeps the collection, and its members are kept as user data."""
    world = await _world(make_world, sample_pack, _ALL)
    await _install(world)
    coll = _live(world, "Everything")
    ada = await _item_id(world, "Ada")
    if edit == "rename":
        coll.name = "Mine"
    elif edit == "describe":
        coll.description = "Changed"
    elif edit == "add_member":
        coll.members.append(uuid.uuid7())
    else:
        coll.members.remove(ada)

    result = await _uninstall(world)

    kept = {(k.kind, k.label, k.reason) for k in result.kept}
    assert (EntityKind.COLLECTION, "Everything", KEEP_EDITED) in kept
    kept_names = {
        n.name for n in await world.graph_repos.nodes.list(after=None, limit=10)
    }
    assert kept_names == kept_items
    for name in kept_items:
        assert (EntityKind.ITEM, name, KEEP_USER_DATA) in kept
    assert result.removed.collections == 0
    assert coll.id in world.collections.collections


async def test_a_users_own_collection_keeps_the_item_it_holds(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """An unedited example collection goes, but an item on the user's own stays."""
    world = await _world(make_world, sample_pack, _ALL)
    await _install(world)
    blue = await _item_id(world, "Blue")
    mine = world.collections.add_users_own("Mine", [blue])

    result = await _uninstall(world)

    assert result.removed.collections == 1
    assert list(world.collections.collections) == [mine]
    assert [(k.kind, k.label, k.reason) for k in result.kept if k.label == "Blue"] == [
        (EntityKind.ITEM, "Blue", KEEP_USER_DATA)
    ]
    names = {n.name for n in await world.graph_repos.nodes.list(after=None, limit=10)}
    assert names == {"Blue"}


async def test_a_collection_the_user_already_deleted_counts_as_removed(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A collection that is already gone is settled without a removal call."""
    world = await _world(make_world, sample_pack, _ALL)
    await _install(world)
    world.collections.collections.clear()

    result = await _uninstall(world)

    assert result.kept == ()
    assert result.removed.collections == 1
    assert "collection" not in world.collections.events
    installation = await world.installations.list_active()
    assert installation == []


async def test_reinstalling_after_removal_creates_the_collections_again(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Removal frees the pack, and a second install makes fresh collections."""
    world = await _world(make_world, sample_pack)
    await _install(world)
    first = set(world.collections.collections)
    await _uninstall(world)

    result = await _install(world)

    assert result.created.collections == 2
    assert len(world.collections.collections) == 2
    assert first.isdisjoint(world.collections.collections)
    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    assert all(
        r.outcome is Outcome.OWNED for r in installation.owned(EntityKind.COLLECTION)
    )
