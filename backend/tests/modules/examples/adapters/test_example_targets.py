import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.ports.pack_targets import Created, RemoveResult
from app.modules.graph.domain.edge import Edge
from app.modules.media.domain.media_attachment import MediaAttachment
from app.modules.presets.domain.preset import Preset

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, SamplePack, World


async def _install_all(
    world: World, sample_pack: SamplePack
) -> tuple[dict[str, uuid.UUID], Created, list[Created], Created, Created, Created]:
    """Create every entity of the sample pack through the targets, in order."""
    pack = sample_pack()
    outcomes = await world.presets.ensure(pack.presets)
    preset_ids = {o.ref: o.entity_id for o in outcomes}
    rel = await world.graph.create_relationship_type(
        pack.relationship_types[0], preset_ids
    )
    types = [await world.graph.create_item_type(t, preset_ids) for t in pack.item_types]
    blue = await world.graph.create_item(pack.items[0], type_slug="demo-record")
    ada = await world.graph.create_item(pack.items[1], type_slug="demo-person")
    edge = await world.graph.create_connection(
        pack.connections[0],
        source_id=blue.entity_id,
        target_id=ada.entity_id,
        type_slug="demo-signed-by",
    )
    return preset_ids, rel, types, blue, ada, edge


async def test_a_preset_that_already_exists_is_reported_as_not_created(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Ensuring identical presets twice creates once and returns the same id."""
    world = make_world()
    first = await world.presets.ensure(sample_pack().presets)
    second = await world.presets.ensure(sample_pack().presets)

    assert first[0].created is True
    assert second[0].created is False
    assert first[0].entity_id == second[0].entity_id


async def test_marker_in_a_schema_becomes_the_preset_id(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A `$preset` marker in a type schema is replaced by the preset's id."""
    world = make_world()
    preset_ids, _, types, *_ = await _install_all(world, sample_pack)

    prop = types[0].content["attributes_schema"]["properties"]["condition"]
    assert prop["x-menagerist"]["list"] == str(preset_ids["grades"])


async def test_inspect_reports_the_content_it_created_with(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Inspecting an item with no connections matches what was created."""
    world = make_world()
    _, _, _, blue, _, edge = await _install_all(world, sample_pack)
    await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)

    inspection = await world.graph.inspect(EntityKind.ITEM, blue.entity_id)

    assert inspection is not None
    assert inspection.content == blue.content
    assert (inspection.has_user_data, inspection.still_in_use) == (False, False)


async def test_item_content_ignores_favourite_but_not_edits(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Starring an item leaves its content alone; renaming it changes it."""
    world = make_world()
    _, _, _, blue, *_ = await _install_all(world, sample_pack)
    node = await world.graph_repos.nodes.get(blue.entity_id)
    assert node is not None

    node.favourite = True
    await world.graph_repos.nodes.save(node)
    starred = await world.graph.inspect(EntityKind.ITEM, blue.entity_id)
    assert starred is not None
    assert starred.content == blue.content

    node.name = "Blue (mine)"
    await world.graph_repos.nodes.save(node)
    renamed = await world.graph.inspect(EntityKind.ITEM, blue.entity_id)
    assert renamed is not None
    assert renamed.content != blue.content


async def test_a_user_connection_counts_as_user_data(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A connection the pack did not create makes the item user-touched."""
    world = make_world()
    _, _, _, blue, _, edge = await _install_all(world, sample_pack)
    await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)
    clean = await world.graph.inspect(EntityKind.ITEM, blue.entity_id)
    assert clean is not None
    assert clean.has_user_data is False

    await world.graph_repos.edges.add(
        Edge.create(source_id=blue.entity_id, target_id=uuid.uuid7(), type="mine")
    )
    touched = await world.graph.inspect(EntityKind.ITEM, blue.entity_id)
    assert touched is not None
    assert touched.has_user_data is True


async def test_an_attached_file_counts_as_user_data(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A file attached to an item makes it user-touched."""
    world = make_world()
    _, _, _, blue, *_ = await _install_all(world, sample_pack)
    await world.media_repos.attachments.add(
        MediaAttachment.for_node(asset_id=uuid.uuid7(), node_id=blue.entity_id)
    )

    inspection = await world.graph.inspect(EntityKind.ITEM, blue.entity_id)

    assert inspection is not None
    assert inspection.has_user_data is True


async def test_a_type_with_live_items_is_in_use(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """An item type is in use until its items are removed."""
    world = make_world()
    _, _, types, blue, *_ = await _install_all(world, sample_pack)
    record_type = types[0].entity_id

    before = await world.graph.inspect(EntityKind.ITEM_TYPE, record_type)
    assert before is not None
    assert before.still_in_use is True

    await world.graph.remove(EntityKind.ITEM, blue.entity_id)
    after = await world.graph.inspect(EntityKind.ITEM_TYPE, record_type)
    assert after is not None
    assert after.still_in_use is False


async def test_relationship_type_in_use_while_a_connection_exists(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A relationship type is refused removal until its connections are gone."""
    world = make_world()
    _, rel, _, _, _, edge = await _install_all(world, sample_pack)
    inspection = await world.graph.inspect(EntityKind.RELATIONSHIP_TYPE, rel.entity_id)
    assert inspection is not None
    assert inspection.still_in_use is True

    refused = await world.graph.remove(EntityKind.RELATIONSHIP_TYPE, rel.entity_id)
    assert refused is RemoveResult.REFUSED_IN_USE

    await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)
    removed = await world.graph.remove(EntityKind.RELATIONSHIP_TYPE, rel.entity_id)
    assert removed is RemoveResult.REMOVED


async def test_remove_twice_reports_already_gone(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Removing an entity again reports it gone, and inspect returns `None`."""
    world = make_world()
    _, _, _, blue, *_ = await _install_all(world, sample_pack)

    first = await world.graph.remove(EntityKind.ITEM, blue.entity_id)
    second = await world.graph.remove(EntityKind.ITEM, blue.entity_id)

    assert first is RemoveResult.REMOVED
    assert second is RemoveResult.ALREADY_GONE
    assert await world.graph.inspect(EntityKind.ITEM, blue.entity_id) is None


async def test_a_preset_a_type_references_cannot_be_removed(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A preset still linked from an item type is refused removal."""
    world = make_world()
    preset_ids, *_ = await _install_all(world, sample_pack)

    result = await world.presets.remove(preset_ids["grades"])

    assert result is RemoveResult.REFUSED_IN_USE


async def test_a_removed_preset_is_gone(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """An unreferenced preset is removed, then reported gone and uninspectable."""
    world = make_world()
    (outcome,) = await world.presets.ensure(sample_pack().presets)

    assert await world.presets.inspect(outcome.entity_id) is not None
    assert await world.presets.remove(outcome.entity_id) is RemoveResult.REMOVED
    assert await world.presets.remove(outcome.entity_id) is RemoveResult.ALREADY_GONE
    assert await world.presets.inspect(outcome.entity_id) is None


async def test_ensuring_no_presets_does_nothing(make_world: MakeWorld) -> None:
    """An empty preset list yields no outcomes."""
    assert await make_world().presets.ensure([]) == []


async def test_unknown_marker_fails_before_anything_is_created(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """An unresolvable marker raises before the type is stored."""
    world = make_world()
    pack = sample_pack()

    with pytest.raises(InvalidPackError, match="unknown preset"):
        await world.graph.create_item_type(pack.item_types[0], {})

    assert await world.graph_repos.node_types.get_by_slug("demo-record") is None


async def test_slug_taken_covers_both_type_kinds_and_unknown_slugs(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Slug checks see live types of both kinds and ignore unknown slugs."""
    world = make_world()
    await _install_all(world, sample_pack)

    assert await world.graph.slug_taken(EntityKind.ITEM_TYPE, "demo-record") is True
    assert (
        await world.graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, "demo-signed-by")
        is True
    )
    assert await world.graph.slug_taken(EntityKind.ITEM_TYPE, "nope") is False


async def test_a_type_and_connection_can_be_removed_and_inspected(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Connections and types inspect as created, and remove cleanly."""
    world = make_world()
    _, rel, types, blue, ada, edge = await _install_all(world, sample_pack)
    expected: dict[EntityKind, Any] = {
        EntityKind.CONNECTION: edge,
        EntityKind.RELATIONSHIP_TYPE: rel,
        EntityKind.ITEM_TYPE: types[1],
    }
    for kind, created in expected.items():
        inspection = await world.graph.inspect(kind, created.entity_id)
        assert inspection is not None
        assert inspection.content == created.content

    await world.graph.remove(EntityKind.ITEM, blue.entity_id)
    await world.graph.remove(EntityKind.ITEM, ada.entity_id)
    # Deleting items does not cascade to their connection.
    assert (
        await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)
        is RemoveResult.REMOVED
    )
    assert (
        await world.graph.remove(EntityKind.ITEM_TYPE, types[1].entity_id)
        is RemoveResult.REMOVED
    )
    assert (
        await world.graph.remove(EntityKind.ITEM_TYPE, types[1].entity_id)
        is RemoveResult.ALREADY_GONE
    )
    assert await world.graph.inspect(EntityKind.CONNECTION, uuid.uuid7()) is None
    assert await world.graph.inspect(EntityKind.ITEM_TYPE, types[1].entity_id) is None


async def test_slug_taken_ignores_removed_types(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Once removed, a type's slug is free again for both type kinds."""
    world = make_world()
    _, rel, types, blue, ada, edge = await _install_all(world, sample_pack)
    for item in (blue, ada):
        await world.graph.remove(EntityKind.ITEM, item.entity_id)
    await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)
    await world.graph.remove(EntityKind.RELATIONSHIP_TYPE, rel.entity_id)
    await world.graph.remove(EntityKind.ITEM_TYPE, types[0].entity_id)

    assert await world.graph.slug_taken(EntityKind.ITEM_TYPE, "demo-record") is False
    assert (
        await world.graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, "demo-signed-by")
        is False
    )


async def test_removing_a_connection_twice_reports_already_gone(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A second connection removal reports it gone."""
    world = make_world()
    *_, edge = await _install_all(world, sample_pack)

    first = await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)
    second = await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)

    assert first is RemoveResult.REMOVED
    assert second is RemoveResult.ALREADY_GONE


async def test_removing_a_deleted_relationship_type_reports_already_gone(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Removing a relationship type that is already deleted reports it gone."""
    world = make_world()
    _, rel, _, _, _, edge = await _install_all(world, sample_pack)
    await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)
    first = await world.graph.remove(EntityKind.RELATIONSHIP_TYPE, rel.entity_id)
    second = await world.graph.remove(EntityKind.RELATIONSHIP_TYPE, rel.entity_id)

    assert first is RemoveResult.REMOVED
    assert second is RemoveResult.ALREADY_GONE


async def test_removing_an_item_type_twice_reports_already_gone(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A second item type removal reports it gone."""
    world = make_world()
    _, _, types, *_ = await _install_all(world, sample_pack)

    first = await world.graph.remove(EntityKind.ITEM_TYPE, types[1].entity_id)
    second = await world.graph.remove(EntityKind.ITEM_TYPE, types[1].entity_id)

    assert first is RemoveResult.REMOVED
    assert second is RemoveResult.ALREADY_GONE


async def test_a_builtin_preset_cannot_be_removed(make_world: MakeWorld) -> None:
    """Built-in presets are refused removal."""
    world = make_world()
    preset = Preset.create(
        kind="choice_list",
        label="Built in",
        definition={"options": ["A"]},
        builtin=True,
    )
    await world.preset_repos.presets.add(preset)

    result = await world.presets.remove(preset.id)

    assert result is RemoveResult.REFUSED_IN_USE


async def test_a_preset_inspection_has_no_flags(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Preset inspections never report user data or use."""
    world = make_world()
    (outcome,) = await world.presets.ensure(sample_pack().presets)

    inspection = await world.presets.inspect(outcome.entity_id)

    assert inspection is not None
    assert (inspection.has_user_data, inspection.still_in_use) == (False, False)


async def test_content_does_not_alias_the_stored_entity(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Editing a stored item in place does not change content captured earlier."""
    world = make_world()
    _, _, _, blue, *_ = await _install_all(world, sample_pack)
    node = await world.graph_repos.nodes.get(blue.entity_id)
    assert node is not None

    node.attributes["condition"] = "Good"
    await world.graph_repos.nodes.save(node)
    inspection = await world.graph.inspect(EntityKind.ITEM, blue.entity_id)

    assert inspection is not None
    assert blue.content["attributes"] == {"condition": "Mint"}
    assert inspection.content != blue.content


async def test_ensure_does_not_read_storage_after_the_import(
    make_world: MakeWorld, sample_pack: SamplePack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ensure` builds its content from the spec, so a failing read cannot orphan."""
    world = make_world()
    existing = sample_pack("pre").presets
    await world.presets.ensure(existing)

    async def boom(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise RuntimeError("read after import")

    monkeypatch.setattr(world.preset_repos.presets, "get", boom)

    created = await world.presets.ensure(sample_pack().presets)
    reused = await world.presets.ensure(existing)

    assert (created[0].created, reused[0].created) == (True, False)
    assert created[0].content["label"] == "demo grades"


async def test_ensure_content_equals_what_inspect_returns_later(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Created and pre-existing presets alike match their later inspection."""
    world = make_world()
    pack = sample_pack()
    created = (await world.presets.ensure(pack.presets))[0]
    reused = (await world.presets.ensure(pack.presets))[0]

    for outcome in (created, reused):
        inspection = await world.presets.inspect(outcome.entity_id)
        assert inspection is not None
        assert outcome.content == inspection.content
