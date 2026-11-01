"""Installing and removing a pack's smart collections, against the fake target."""

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
from app.modules.examples.domain.errors import (
    InstallFailedError,
    PackAlreadyInstalledError,
    SlugClashError,
)
from app.modules.examples.domain.installation import EntityKind, Outcome
from app.modules.examples.domain.pack import ExamplePack, PackCollection
from app.modules.examples.domain.removal import KEEP_EDITED
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from tests.modules.examples.conftest import (
        FakeCollection,
        MakeWorld,
        SamplePack,
        World,
    )

_RULE: dict[str, Any] = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "type", "in": ["demo-record"]}]},
}
_MANUAL = PackCollection(ref="both", name="Both", item_refs=("ada", "blue"))
_SMART = PackCollection(
    ref="records", name="Records", description="All records", definition=_RULE
)


def _pack(sample_pack: SamplePack) -> ExamplePack:
    return replace(sample_pack(), collections=(_MANUAL, _SMART))


async def _install(world: World) -> InstallResult:
    return await InstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id="demo"), world.actor)


async def _uninstall(world: World) -> UninstallResult:
    return await UninstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id="demo"), world.actor)


def _live(world: World, name: str) -> FakeCollection:
    return next(c for c in world.collections.collections.values() if c.name == name)


async def _item_count(world: World) -> int:
    nodes = await world.graph_repos.nodes.list(
        scope=ContentFilter.everyone(), after=None, limit=10
    )
    return len(nodes)


async def test_install_creates_a_manual_and_a_smart_collection(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The smart one keeps the pack's definition and holds no items."""
    world = make_world(_pack(sample_pack))

    result = await _install(world)

    assert result.created.collections == 2
    assert result.created.items == 2
    smart = _live(world, "Records")
    assert smart.definition == _RULE
    assert smart.members == []
    assert smart.description == "All records"
    assert len(_live(world, "Both").members) == 2
    assert [(s.ref, ids) for s, ids in world.collections.create_calls][1] == (
        "records",
        [],
    )


async def test_a_failing_smart_collection_rolls_the_whole_install_back(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """If the definition is refused, nothing is left, manual collection included."""
    world = make_world(_pack(sample_pack))
    world.collections.fail_on_call = 2

    with pytest.raises(InstallFailedError, match="collection boom"):
        await _install(world)

    assert world.collections.collections == {}
    assert await _item_count(world) == 0
    assert await world.graph_repos.node_types.list(after=None, limit=10) == []
    assert (
        await world.installations.get_active_for_pack(
            "demo", scope=ContentFilter.everyone()
        )
        is None
    )


async def test_installing_twice_does_not_duplicate_the_smart_collection(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The second install is refused and the first install's collections stay."""
    world = make_world(_pack(sample_pack))
    await _install(world)

    with pytest.raises(PackAlreadyInstalledError):
        await _install(world)

    assert sorted(c.name for c in world.collections.collections.values()) == [
        "Both",
        "Records",
    ]
    assert len(world.collections.create_calls) == 2


async def test_a_clashing_type_slug_never_half_installs_a_smart_collection(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A taken type slug stops the install before any collection is made."""
    world = make_world(_pack(sample_pack))
    await world.graph_repos.node_types.add(
        NodeType.create(slug="demo-record", label="Mine")
    )

    with pytest.raises(SlugClashError):
        await _install(world)

    assert world.collections.create_calls == []
    assert world.collections.collections == {}
    assert await _item_count(world) == 0
    assert (
        await world.installations.get_active_for_pack(
            "demo", scope=ContentFilter.everyone()
        )
        is None
    )


async def test_uninstall_removes_the_smart_collection_and_every_item(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A smart collection has no members, so it never keeps an item."""
    world = make_world(_pack(sample_pack))
    await _install(world)

    result = await _uninstall(world)

    assert result.kept == ()
    assert result.removed.collections == 2
    assert world.collections.collections == {}
    assert await _item_count(world) == 0


async def test_reinstalling_after_removal_recreates_the_smart_collection(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Removal frees the pack and a second install makes a fresh smart one."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    first = _live(world, "Records").id
    await _uninstall(world)

    result = await _install(world)

    assert result.created.collections == 2
    again = _live(world, "Records")
    assert again.id != first
    assert again.definition == _RULE
    installation = await world.installations.get_active_for_pack(
        "demo", scope=ContentFilter.everyone()
    )
    assert installation is not None
    assert all(
        r.outcome is Outcome.OWNED for r in installation.owned(EntityKind.COLLECTION)
    )


async def test_an_edited_definition_is_kept_on_uninstall(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Changing the definition counts as an edit, as renaming does."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    smart = _live(world, "Records")
    smart.definition = {"v": 1, "where": None}

    result = await _uninstall(world)

    assert (EntityKind.COLLECTION, "Records", KEEP_EDITED) in {
        (k.kind, k.label, k.reason) for k in result.kept
    }
    assert smart.id in world.collections.collections
    assert result.removed.collections == 1
