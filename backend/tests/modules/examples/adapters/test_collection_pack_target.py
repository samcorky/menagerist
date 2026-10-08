"""The real collection target and the graph target's collection rules, in memory."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.example_targets import (
    CollectionPackTarget,
    GraphPackTarget,
    build_in_memory_collections_repos,
    in_memory_collection_stores,
    in_memory_graph_stores,
)
from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import PackCollection
from app.modules.examples.ports.pack_targets import RemoveResult
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.modules.collections.ports.unit_of_work import CollectionsRepos
    from tests.modules.examples.conftest import MakeWorld, SamplePack, World


class Rig:
    """A real collection target and graph target over shared in-memory storage."""

    def __init__(
        self,
        *,
        world: World,
        repos: CollectionsRepos,
        target: CollectionPackTarget,
        graph: GraphPackTarget,
        blue: uuid.UUID,
        ada: uuid.UUID,
    ) -> None:
        self.world = world
        self.repos = repos
        self.target = target
        self.graph = graph
        self.blue = blue
        self.ada = ada


_SPEC = PackCollection(ref="c", name="Both", description="Two", item_refs=("a", "b"))


async def _rig(make_world: MakeWorld, sample_pack: SamplePack) -> Rig:
    world = make_world()
    repos = build_in_memory_collections_repos()
    pack = sample_pack()
    presets = {o.ref: o.entity_id for o in await world.presets.ensure(pack.presets)}
    for item_type in pack.item_types:
        await world.graph.create_item_type(item_type, presets)
    blue = await world.graph.create_item(pack.items[0], type_slug="demo-record")
    ada = await world.graph.create_item(pack.items[1], type_slug="demo-person")
    return Rig(
        world=world,
        repos=repos,
        target=CollectionPackTarget(
            in_memory_collection_stores(repos, world.graph_repos)
        ),
        graph=GraphPackTarget(
            in_memory_graph_stores(
                world.graph_repos, world.media_repos, world.preset_repos, repos
            )
        ),
        blue=blue.entity_id,
        ada=ada.entity_id,
    )


async def test_create_returns_the_stored_content(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Content has the stored name, description and sorted member ids."""
    rig = await _rig(make_world, sample_pack)

    created = await rig.target.create_collection(_SPEC, item_ids=[rig.blue, rig.ada])

    assert created.content == {
        "name": "Both",
        "description": "Two",
        "members": sorted([str(rig.blue), str(rig.ada)]),
    }
    inspection = await rig.target.inspect(created.entity_id)
    assert inspection is not None
    assert inspection.content == created.content
    assert (inspection.has_user_data, inspection.still_in_use) == (False, False)


async def test_slugs_are_derived_and_never_clash(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A second collection with the same name gets a suffixed slug."""
    rig = await _rig(make_world, sample_pack)

    first = await rig.target.create_collection(_SPEC, item_ids=[rig.blue])
    second = await rig.target.create_collection(_SPEC, item_ids=[rig.blue])

    slugs = []
    for created in (first, second):
        stored = await rig.repos.collections.get(created.entity_id)
        assert stored is not None
        slugs.append(stored.slug.value)
    assert slugs == ["both", "both-2"]


async def test_a_deleted_member_changes_the_content(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Members count only live items, so a deleted item reads as an edit."""
    rig = await _rig(make_world, sample_pack)
    created = await rig.target.create_collection(_SPEC, item_ids=[rig.blue, rig.ada])

    await rig.graph.remove(EntityKind.ITEM, rig.ada)
    inspection = await rig.target.inspect(created.entity_id)

    assert inspection is not None
    assert inspection.content != created.content
    assert inspection.content["members"] == [str(rig.blue)]


async def test_remove_then_inspect_and_remove_again(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A removed collection inspects as gone and removes as already gone."""
    rig = await _rig(make_world, sample_pack)
    created = await rig.target.create_collection(_SPEC, item_ids=[rig.blue])

    assert await rig.target.remove(created.entity_id) is RemoveResult.REMOVED
    assert await rig.target.inspect(created.entity_id) is None
    assert await rig.target.remove(created.entity_id) is RemoveResult.ALREADY_GONE
    assert await rig.target.inspect(uuid.uuid7()) is None


async def test_a_failed_item_add_leaves_no_collection_behind(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """An unknown item id aborts the create and removes the empty collection."""
    rig = await _rig(make_world, sample_pack)

    with pytest.raises(ValidationError):
        await rig.target.create_collection(_SPEC, item_ids=[rig.blue, uuid.uuid7()])

    assert await rig.repos.collections.list(after=None, limit=10) == []


async def test_an_item_on_a_live_collection_is_user_data(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Membership of any live collection marks the item; deleting it clears that."""
    rig = await _rig(make_world, sample_pack)
    before = await rig.graph.inspect(EntityKind.ITEM, rig.ada)
    assert before is not None
    assert before.has_user_data is False

    created = await rig.target.create_collection(_SPEC, item_ids=[rig.ada])
    held = await rig.graph.inspect(EntityKind.ITEM, rig.ada)
    assert held is not None
    assert held.has_user_data is True

    await rig.target.remove(created.entity_id)
    released = await rig.graph.inspect(EntityKind.ITEM, rig.ada)
    assert released is not None
    assert released.has_user_data is False


@pytest.mark.parametrize("kind", [EntityKind.PRESET, EntityKind.COLLECTION])
async def test_the_graph_target_rejects_kinds_it_does_not_handle(
    make_world: MakeWorld, sample_pack: SamplePack, kind: EntityKind
) -> None:
    """Inspecting or removing a kind owned by another target fails loudly."""
    rig = await _rig(make_world, sample_pack)

    with pytest.raises(ValueError, match="does not handle"):
        await rig.graph.inspect(kind, uuid.uuid7())
    with pytest.raises(ValueError, match="does not handle"):
        await rig.graph.remove(kind, uuid.uuid7())
