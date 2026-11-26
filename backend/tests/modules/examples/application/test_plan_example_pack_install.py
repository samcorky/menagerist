"""A dry run reports what an install would do, and writes nothing."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.application.plan_example_pack_install import (
    PlanExamplePackInstall,
    PlanExamplePackInstallQuery,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
)
from app.modules.examples.domain.errors import PackNotFoundError
from app.modules.examples.domain.pack import ExamplePack
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.modules.graph.domain.node_type import NodeType
from app.modules.transfer.domain.bundle import BundleConnection, BundleCover, BundleItem
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import Plan, PlanAction
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.paging import PageRequest

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, SamplePack, World


async def _plan(world: World, pack_id: str = "demo") -> Plan:
    return await PlanExamplePackInstall(
        ExampleRepos(runs=world.runs),
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(PlanExamplePackInstallQuery(pack_id=pack_id), world.actor)


async def _install(world: World, pack_id: str = "demo") -> None:
    await InstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id=pack_id), world.actor)


async def _uninstall(world: World) -> None:
    await UninstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id="demo"), world.actor)


def _actions(plan: Plan) -> list[tuple[EntityKind, str, PlanAction]]:
    return [(e.kind, e.ref, e.action) for e in plan.entities]


async def _rename_item(world: World, old: str, new: str) -> None:
    nodes = await world.graph_repos.nodes.list(
        scope=ContentFilter.everyone(), after=None, limit=10
    )
    node = next(n for n in nodes if n.name == old)
    node.name = new
    await world.graph_repos.nodes.save(node)


async def test_a_fresh_pack_plans_to_create_everything_in_install_order(
    make_world: MakeWorld,
) -> None:
    """Every entity is to be created, presets first and connections after items."""
    world = make_world()

    plan = await _plan(world)

    assert plan.ready is True
    assert plan.blockers == ()
    assert _actions(plan) == [
        (EntityKind.PRESET, "grades", PlanAction.CREATE),
        (EntityKind.RELATIONSHIP_TYPE, "signed-by", PlanAction.CREATE),
        (EntityKind.ITEM_TYPE, "record", PlanAction.CREATE),
        (EntityKind.ITEM_TYPE, "person", PlanAction.CREATE),
        (EntityKind.ITEM, "blue", PlanAction.CREATE),
        (EntityKind.ITEM, "ada", PlanAction.CREATE),
        (EntityKind.CONNECTION, "connection-0", PlanAction.CREATE),
    ]
    assert plan.entities[-1].label == "Blue to Ada"


async def test_planning_writes_nothing(make_world: MakeWorld) -> None:
    """No run is recorded and nothing is created."""
    world = make_world()

    await _plan(world)

    assert (
        await world.runs.list_for_bundle("demo", scope=ContentFilter.everyone()) == []
    )
    assert (
        await world.graph_repos.nodes.list(
            scope=ContentFilter.everyone(), after=None, limit=10
        )
        == []
    )
    assert (
        await world.preset_repos.presets.list(
            scope=ContentFilter.everyone(), page=PageRequest(limit=10)
        )
    ).items == []


async def test_an_unknown_pack_is_not_found(make_world: MakeWorld) -> None:
    """An id the catalogue lacks is not found."""
    with pytest.raises(PackNotFoundError):
        await _plan(make_world(), "nope")


async def test_an_installed_pack_is_blocked_and_lists_nothing(
    make_world: MakeWorld,
) -> None:
    """The blocker names the error the install would raise."""
    world = make_world()
    await _install(world)

    plan = await _plan(world)

    assert plan.ready is False
    assert plan.entities == ()
    [blocker] = plan.blockers
    assert blocker.code == "PackAlreadyInstalledError"
    assert "already installed" in blocker.reason


async def test_a_taken_type_slug_is_a_conflict_on_that_type(
    make_world: MakeWorld,
) -> None:
    """The clash is on the entity, with the install's message; the rest still plans."""
    world = make_world()
    await world.graph_repos.node_types.add(
        NodeType.create(owner_id=world.actor.id, slug="demo-record", label="Mine")
    )

    plan = await _plan(world)

    assert plan.ready is False
    assert plan.blockers == ()
    [conflict] = plan.conflicts
    assert (conflict.kind, conflict.ref) == (EntityKind.ITEM_TYPE, "record")
    assert conflict.reason is not None
    assert "'demo-record'" in conflict.reason
    assert len(plan.with_action(PlanAction.CREATE)) == 6


async def test_an_identical_preset_the_person_has_is_unchanged(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A saved list the same as the pack's is used, not created again."""
    world = make_world()
    await world.presets.ensure(sample_pack().presets)

    plan = await _plan(world)

    preset = plan.entities[0]
    assert (preset.kind, preset.action) == (EntityKind.PRESET, PlanAction.UNCHANGED)
    assert preset.reason == "You already have one the same."


async def test_what_an_earlier_removal_kept_is_taken_back_unchanged(
    make_world: MakeWorld,
) -> None:
    """The kept item, its type and the list it uses come back; a new link is made."""
    world = make_world()
    await _install(world)
    await _rename_item(world, "Blue", "Mine now")
    await _uninstall(world)

    plan = await _plan(world)

    assert plan.ready is True
    unchanged = {(e.kind, e.ref) for e in plan.with_action(PlanAction.UNCHANGED)}
    assert unchanged == {
        (EntityKind.PRESET, "grades"),
        (EntityKind.ITEM_TYPE, "record"),
        (EntityKind.ITEM, "blue"),
    }
    connection = plan.entities[-1]
    assert connection.action is PlanAction.CREATE
    assert connection.label == "Mine now to Ada"


async def test_a_kept_connection_between_kept_items_is_unchanged(
    make_world: MakeWorld,
) -> None:
    """An edited connection keeps both its ends, so all three are taken back."""
    world = make_world()
    await _install(world)
    [edge] = (
        await world.graph_repos.edges.list(
            scope=ContentFilter.everyone(), page=PageRequest(limit=10)
        )
    ).items
    edge.attributes = {"note": "mine"}
    await world.graph_repos.edges.save(edge)
    await _uninstall(world)

    plan = await _plan(world)

    assert plan.entities[-1].action is PlanAction.UNCHANGED


async def test_an_add_on_without_its_base_is_blocked_but_still_listed(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The blocker names the missing set; its own entities are still planned."""
    add_on = ExamplePack(
        id="extras",
        requires=("demo",),
        items=(BundleItem(ref="x", type_ref="demo:person", name="Extra X"),),
        connections=(
            BundleConnection(
                source_ref="x", target_ref="demo:blue", type_ref="demo:signed-by"
            ),
        ),
    )
    world = make_world(sample_pack(), add_on)

    plan = await _plan(world, "extras")

    [blocker] = plan.blockers
    assert blocker.code == "RequirementsNotMetError"
    assert blocker.reason == "Add Demo first."
    assert _actions(plan) == [
        (EntityKind.ITEM, "x", PlanAction.CREATE),
        (EntityKind.CONNECTION, "connection-0", PlanAction.CREATE),
    ]
    assert plan.entities[-1].label == "Extra X to demo:blue"


async def test_an_add_on_with_its_base_names_the_base_items(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A link to a base item is labelled with that item's name."""
    add_on = ExamplePack(
        id="extras",
        requires=("demo",),
        items=(BundleItem(ref="x", type_ref="demo:person", name="Extra X"),),
        connections=(
            BundleConnection(
                source_ref="x", target_ref="demo:blue", type_ref="demo:signed-by"
            ),
        ),
    )
    world = make_world(sample_pack(), add_on)
    await _install(world)

    plan = await _plan(world, "extras")

    assert plan.ready is True
    assert plan.entities[-1].label == "Extra X to Blue"


def _covered(sample_pack: SamplePack) -> ExamplePack:
    pack = sample_pack()
    record = replace(pack.item_types[0], cover=BundleCover(style="sleeve"))
    return replace(pack, item_types=(record, pack.item_types[1]))


async def test_an_item_of_a_type_with_a_cover_style_plans_a_cover(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Covers come last, one for each item whose type has a style."""
    world = make_world(_covered(sample_pack))

    plan = await _plan(world)

    assert _actions(plan)[-1] == (EntityKind.COVER, "blue", PlanAction.CREATE)
    assert [e.kind for e in plan.entities].count(EntityKind.COVER) == 1
