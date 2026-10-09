from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.domain.errors import (
    InstallFailedError,
    PackAlreadyInstalledError,
    PackNotFoundError,
    SlugClashError,
)
from app.modules.examples.domain.installation import (
    EntityKind,
    Installation,
    InstallationStatus,
)
from app.modules.examples.domain.pack import PackPreset
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, SamplePack, World

_COMMAND = InstallExamplePackCommand(pack_id="demo")


def _use_case(world: World) -> InstallExamplePack:
    return InstallExamplePack(
        world.uow,
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    )


async def _active(world: World, pack_id: str = "demo") -> Installation:
    installation = await world.installations.get_active_for_pack(pack_id)
    assert installation is not None
    return installation


def _capture_installations(world: World) -> list[Installation]:
    """Collect every installation added, so a FAILED one can be inspected."""
    recorded: list[Installation] = []
    original = world.installations.add

    async def add(installation: Installation) -> None:
        recorded.append(installation)
        await original(installation)

    world.installations.add = add  # type: ignore[method-assign]
    return recorded


async def _assert_nothing_left(world: World) -> None:
    assert await world.installations.get_active_for_pack("demo") is None
    assert await world.graph_repos.node_types.list(after=None, limit=10) == []
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []
    assert await world.graph_repos.edges.list(after=None, limit=10) == []
    assert await world.graph_repos.edge_types.list(after=None, limit=10) == []
    assert await world.preset_repos.presets.list(after=None, limit=10) == []


async def test_install_creates_everything_and_records_it(
    make_world: MakeWorld,
) -> None:
    """An install creates every entity, records each, and commits."""
    world = make_world()

    result = await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)

    counts = result.created
    assert (counts.presets, counts.relationship_types, counts.item_types) == (1, 1, 2)
    assert (counts.items, counts.connections) == (2, 1)
    installation = await _active(world)
    assert installation.status is InstallationStatus.INSTALLED
    assert len(installation.owned()) == 7
    assert await world.graph_repos.nodes.list(after=None, limit=10)
    assert len(await world.graph_repos.node_types.list(after=None, limit=10)) == 2
    assert world.uow.committed is True


async def test_every_created_entity_is_hashed_for_later_comparison(
    make_world: MakeWorld,
) -> None:
    """Each record carries a SHA-256 of what was created."""
    world = make_world()
    await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)
    assert all(len(r.content_hash) == 64 for r in (await _active(world)).owned())


async def test_unknown_pack_is_not_found(make_world: MakeWorld) -> None:
    """An id the catalogue lacks is not found."""
    with pytest.raises(PackNotFoundError):
        await _use_case(make_world()).handle(
            InstallExamplePackCommand(pack_id="nope"), SYSTEM_ACTOR
        )


async def test_installing_twice_is_a_conflict(make_world: MakeWorld) -> None:
    """A second install of an installed pack conflicts."""
    world = make_world()
    await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)
    with pytest.raises(PackAlreadyInstalledError):
        await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)


@pytest.mark.parametrize(
    ("repo", "slug", "kind_phrase"),
    [
        ("node_types", "demo-record", "an item type"),
        ("edge_types", "demo-signed-by", "a relationship type"),
    ],
)
async def test_a_slug_clash_creates_nothing_and_names_the_slug(
    make_world: MakeWorld, repo: str, slug: str, kind_phrase: str
) -> None:
    """A taken slug aborts before anything is created and is named."""
    world = make_world()
    if repo == "node_types":
        await world.graph_repos.node_types.add(NodeType.create(slug=slug, label="Mine"))
    else:
        await world.graph_repos.edge_types.add(EdgeType.create(slug=slug, label="Mine"))

    with pytest.raises(SlugClashError) as excinfo:
        await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)

    assert excinfo.value.slug == slug
    assert kind_phrase in str(excinfo.value)
    assert await world.installations.get_active_for_pack("demo") is None
    assert await world.preset_repos.presets.list(after=None, limit=10) == []
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []


async def test_an_identical_existing_preset_is_used_but_not_owned(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A preset that already exists is reused and not recorded as the pack's."""
    world = make_world()
    existing = await world.presets.ensure(sample_pack().presets)

    await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)

    installation = await _active(world)
    assert installation.owned(EntityKind.PRESET) == []
    assert existing[0].created is True  # created by the test, not by the pack


# The sample pack has 1 preset, 1 relationship type, 2 item types, 2 items and
# 1 connection: a failure at the start and at the end of each step.
@pytest.mark.parametrize(
    ("method", "fail_on_call"),
    [
        ("ensure", 1),
        ("create_relationship_type", 1),
        ("create_item_type", 1),
        ("create_item_type", 2),
        ("create_item", 1),
        ("create_item", 2),
        ("create_connection", 1),
    ],
)
async def test_a_failure_rolls_everything_back(
    make_world: MakeWorld, method: str, fail_on_call: int
) -> None:
    """Whichever step fails, everything created so far is removed."""
    world = make_world()
    target = world.presets if method == "ensure" else world.graph
    original = getattr(target, method)
    calls = 0

    async def flaky(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise RuntimeError("boom")
        return await original(*args, **kwargs)

    setattr(target, method, flaky)
    recorded = _capture_installations(world)

    with pytest.raises(InstallFailedError, match="boom") as excinfo:
        await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)

    assert calls == fail_on_call  # the injected failure really happened
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert await world.installations.list_active() == []
    assert recorded[0].status is InstallationStatus.FAILED
    await _assert_nothing_left(world)


async def test_a_rollback_that_cannot_finish_leaves_the_install_resumable(
    make_world: MakeWorld,
) -> None:
    """If the undo fails too, the installation stays INSTALLING with its records."""
    world = make_world()

    async def broken_remove(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise RuntimeError("database down")

    async def fail_connection(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise RuntimeError("boom")

    world.graph.create_connection = fail_connection  # type: ignore[method-assign]
    world.graph.remove = broken_remove  # type: ignore[method-assign]

    with pytest.raises(InstallFailedError, match="Remove the examples") as excinfo:
        await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)

    assert isinstance(excinfo.value.__cause__, RuntimeError)
    installation = await _active(world)
    assert installation.status is InstallationStatus.INSTALLING
    assert installation.owned()  # recorded, so uninstall can finish the job


async def test_a_rollback_keeps_what_the_user_changed_and_says_so(
    make_world: MakeWorld,
) -> None:
    """An entity edited mid-install is kept, and the error says so."""
    world = make_world()

    async def edit_then_fail(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        node_type = (await world.graph_repos.node_types.list(after=None, limit=10))[0]
        node_type.label = "Renamed by me"
        await world.graph_repos.node_types.save(node_type)
        raise RuntimeError("boom")

    world.graph.create_connection = edit_then_fail  # type: ignore[method-assign]

    with pytest.raises(InstallFailedError, match="you had changed were kept"):
        await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)

    remaining = await world.graph_repos.node_types.list(after=None, limit=10)
    assert [t.label for t in remaining] == ["Renamed by me"]


async def test_an_unfinished_installation_blocks_a_second_install(
    make_world: MakeWorld,
) -> None:
    """A crash-orphaned INSTALLING record blocks another install."""
    world = make_world()
    await world.installations.add(Installation.start("demo"))
    with pytest.raises(PackAlreadyInstalledError):
        await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)


async def test_a_crash_between_create_and_record_is_named_by_the_next_install(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """One orphan can be left by a crash; the slug pre-flight then names it."""
    world = make_world()
    await world.graph.create_item_type(sample_pack().item_types[1], {})
    with pytest.raises(SlugClashError, match="demo-person"):
        await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)


async def test_every_preset_is_recorded_before_the_first_save_and_rolled_back(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """All presets `ensure` created are owned, and all go if a later step fails."""
    base = sample_pack()
    pack = replace(
        base,
        presets=(
            *base.presets,
            PackPreset(
                ref="formats",
                kind="choice_list",
                label="demo formats",
                definition={"options": ["LP", "CD"]},
            ),
        ),
    )
    world = make_world(pack)
    await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)
    assert len((await _active(world)).owned(EntityKind.PRESET)) == 2

    failing = make_world(pack)

    async def fail_first_item(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise RuntimeError("boom")

    failing.graph.create_item = fail_first_item  # type: ignore[method-assign]
    with pytest.raises(InstallFailedError, match="boom"):
        await _use_case(failing).handle(_COMMAND, SYSTEM_ACTOR)
    await _assert_nothing_left(failing)


async def test_a_persist_failure_right_after_ensure_is_rolled_back(
    make_world: MakeWorld,
) -> None:
    """Presets `ensure` committed are already recorded, so a failed save undoes them."""
    world = make_world()
    original = world.installations.save
    calls = 0

    async def fail_first_save(installation: Installation) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("save failed")
        await original(installation)

    world.installations.save = fail_first_save  # type: ignore[method-assign]

    with pytest.raises(InstallFailedError, match="save failed"):
        await _use_case(world).handle(_COMMAND, SYSTEM_ACTOR)

    assert calls >= 1
    await _assert_nothing_left(world)
