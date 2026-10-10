"""Add-on packs: installing against a required pack, and removal order."""

from typing import TYPE_CHECKING

import pytest

from app.modules.examples.application.external_refs import resolve_external_refs
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
    InstallResult,
    installation_counts,
)
from app.modules.examples.application.required_by import dependants_by_pack
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
    UninstallResult,
)
from app.modules.examples.domain.errors import (
    InstallFailedError,
    RequiredByInstalledPackError,
    RequirementsNotMetError,
)
from app.modules.examples.domain.installation import (
    EntityKind,
    Installation,
    InstallationStatus,
    Outcome,
)
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackCollection,
    PackConnection,
    PackCover,
    PackItem,
    PackItemType,
    PackRelationshipType,
)
from app.modules.examples.domain.removal import KEEP_EDITED, KEEP_USER_DATA
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node
    from tests.modules.examples.conftest import MakeWorld, World


def _base(pack_id: str, *, cover: str | None = None) -> ExamplePack:
    """A base pack: one item type, one relationship type, two items, one link."""
    title = pack_id.title()
    style = None if cover is None else PackCover(style=cover)
    return ExamplePack(
        id=pack_id,
        relationship_types=(
            PackRelationshipType(
                ref="link", slug=f"{pack_id}-link", label="Link", reverse_label="Back"
            ),
        ),
        item_types=(
            PackItemType(
                ref="thing",
                slug=f"{pack_id}-thing",
                label=f"{title} thing",
                cover=style,
            ),
        ),
        items=(
            PackItem(ref="a", type_ref="thing", name=f"{title} A"),
            PackItem(ref="b", type_ref="thing", name=f"{title} B"),
        ),
        connections=(PackConnection(source_ref="a", target_ref="b", type_ref="link"),),
    )


def _extras() -> ExamplePack:
    """An add-on of `games`: own type and items, using the base's type and items."""
    return ExamplePack(
        id="extras",
        requires=("games",),
        relationship_types=(
            PackRelationshipType(
                ref="own", slug="extras-own", label="Own", reverse_label="Owned"
            ),
        ),
        item_types=(PackItemType(ref="extra", slug="extras-extra", label="Extra"),),
        items=(
            PackItem(ref="x", type_ref="extra", name="Extra X"),
            PackItem(ref="y", type_ref="games:thing", name="Extra Y"),
        ),
        connections=(
            PackConnection(source_ref="x", target_ref="games:a", type_ref="games:link"),
            PackConnection(source_ref="y", target_ref="x", type_ref="own"),
        ),
        collections=(
            PackCollection(ref="mix", name="Mix", item_refs=("games:b", "x")),
        ),
    )


def _bridge() -> ExamplePack:
    """A bridge add-on: only connections between two required packs."""
    return ExamplePack(
        id="tie",
        requires=("games", "music"),
        connections=(
            PackConnection(
                source_ref="games:a", target_ref="music:b", type_ref="games:link"
            ),
        ),
    )


def _world(make_world: MakeWorld, *extra: ExamplePack) -> World:
    return make_world(_base("games"), _base("music"), _extras(), _bridge(), *extra)


async def _install(world: World, pack_id: str) -> InstallResult:
    return await InstallExamplePack(
        world.uow,
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id=pack_id), SYSTEM_ACTOR)


async def _uninstall(world: World, pack_id: str) -> UninstallResult:
    return await UninstallExamplePack(
        world.uow,
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id=pack_id), SYSTEM_ACTOR)


async def _node(world: World, name: str) -> Node:
    nodes = await world.graph_repos.nodes.list(after=None, limit=50)
    return next(n for n in nodes if n.name == name)


async def _names(world: World) -> list[str]:
    nodes = await world.graph_repos.nodes.list(after=None, limit=50)
    return sorted(n.name for n in nodes)


async def _edge_pairs(world: World) -> set[tuple[str, str]]:
    edges = await world.graph_repos.edges.list(after=None, limit=50)
    by_id = {
        n.id: n.name for n in await world.graph_repos.nodes.list(after=None, limit=50)
    }
    return {(by_id[e.source_id], by_id[e.target_id]) for e in edges}


async def _snapshot(world: World) -> tuple[list[str], int, int, int]:
    """Everything an install could have created."""
    return (
        await _names(world),
        len(await world.graph_repos.node_types.list(after=None, limit=50)),
        len(await world.graph_repos.edges.list(after=None, limit=50)),
        len(world.collections.collections),
    )


async def _installation(world: World, pack_id: str) -> Installation:
    installation = await world.installations.get_active_for_pack(pack_id)
    assert installation is not None
    return installation


async def test_add_on_is_refused_without_its_base(make_world: MakeWorld) -> None:
    """The refusal names the missing pack, and nothing is created or recorded."""
    world = _world(make_world)

    with pytest.raises(RequirementsNotMetError, match=r"Add Games first\."):
        await _install(world, "extras")

    assert await _snapshot(world) == ([], 0, 0, 0)
    assert await world.installations.list_for_pack("extras") == []


async def test_add_on_is_refused_while_its_base_is_half_installed(
    make_world: MakeWorld,
) -> None:
    """An unfinished installation of the base does not count."""
    world = _world(make_world)
    await world.installations.add(Installation.start("games"))

    with pytest.raises(RequirementsNotMetError, match=r"Add Games first\."):
        await _install(world, "extras")

    assert await world.installations.list_for_pack("extras") == []


async def test_add_on_installs_against_its_base(make_world: MakeWorld) -> None:
    """It creates only its own entities, connected to the base's items."""
    world = _world(make_world)
    await _install(world, "games")
    base_before = list((await _installation(world, "games")).entities)

    result = await _install(world, "extras")

    assert (result.created.items, result.created.connections) == (2, 2)
    assert (result.created.item_types, result.created.relationship_types) == (1, 1)
    assert result.created.collections == 1
    assert await _names(world) == ["Extra X", "Extra Y", "Games A", "Games B"]
    assert {("Extra X", "Games A"), ("Extra Y", "Extra X")} <= await _edge_pairs(world)
    assert (await _node(world, "Extra Y")).type == "games-thing"
    assert (await _node(world, "Extra X")).type == "extras-extra"
    assert list((await _installation(world, "games")).entities) == base_before


async def test_a_collection_can_mix_base_and_add_on_items(
    make_world: MakeWorld,
) -> None:
    """The add-on's collection holds an item of each pack."""
    world = _world(make_world)
    await _install(world, "games")
    await _install(world, "extras")

    (collection,) = world.collections.collections.values()

    expected = {(await _node(world, n)).id for n in ("Games B", "Extra X")}
    assert set(collection.members) == expected


async def test_external_entities_are_never_recorded_by_the_add_on(
    make_world: MakeWorld,
) -> None:
    """Counts and records cover the add-on's own entities only."""
    world = _world(make_world)
    await _install(world, "games")
    await _install(world, "extras")

    installation = await _installation(world, "extras")

    assert all(":" not in r.ref for r in installation.entities)
    games_ids = {r.entity_id for r in (await _installation(world, "games")).entities}
    assert not games_ids & {r.entity_id for r in installation.entities}
    counts = installation_counts(installation)
    assert (counts.items, counts.item_types, counts.connections) == (2, 1, 2)
    assert (counts.relationship_types, counts.collections) == (1, 1)


async def test_a_bridge_resolves_from_two_packs(make_world: MakeWorld) -> None:
    """A connection can join an item of one required pack to another's."""
    world = _world(make_world)
    await _install(world, "games")

    with pytest.raises(RequirementsNotMetError, match=r"Add Music first\."):
        await _install(world, "tie")
    await _install(world, "music")
    result = await _install(world, "tie")

    assert (result.created.connections, result.created.items) == (1, 0)
    assert ("Games A", "Music B") in await _edge_pairs(world)


async def test_a_deleted_base_item_is_named_and_nothing_is_created(
    make_world: MakeWorld,
) -> None:
    """The person deleted Games A: the add-on says so before creating anything."""
    world = _world(make_world)
    await _install(world, "games")
    await world.graph.remove(EntityKind.ITEM, (await _node(world, "Games A")).id)
    before = await _snapshot(world)

    with pytest.raises(RequirementsNotMetError, match=r"Games no longer has Games A\."):
        await _install(world, "extras")

    assert await _snapshot(world) == before
    assert world.collections.create_calls == []
    assert await world.installations.list_for_pack("extras") == []


async def test_a_replaced_base_item_is_refused(make_world: MakeWorld) -> None:
    """A fresh item with the same name is not the one the base pack created."""
    world = _world(make_world)
    await _install(world, "games")
    await world.graph.remove(EntityKind.ITEM, (await _node(world, "Games A")).id)
    await world.graph.create_item(
        PackItem(ref="again", type_ref="thing", name="Games A"),
        type_slug="games-thing",
    )
    assert "Games A" in await _names(world)

    with pytest.raises(RequirementsNotMetError, match=r"Games no longer has Games A\."):
        await _install(world, "extras")

    assert await world.installations.list_for_pack("extras") == []


async def test_an_edited_base_item_still_resolves(make_world: MakeWorld) -> None:
    """Editing the base item does not stop the add-on; its new name is used."""
    world = _world(make_world)
    await _install(world, "games")
    a = await _node(world, "Games A")
    a.name = "Mine now"
    await world.graph_repos.nodes.save(a)

    await _install(world, "extras")

    assert ("Extra X", "Mine now") in await _edge_pairs(world)
    installation = await _installation(world, "extras")
    labels = {r.label for r in installation.owned(EntityKind.CONNECTION)}
    assert "Extra X to Mine now" in labels


async def test_a_deleted_base_type_is_named(make_world: MakeWorld) -> None:
    """An add-on that needs only a base item type names it when it has gone."""
    typed = ExamplePack(
        id="typed",
        requires=("games",),
        items=(PackItem(ref="t", type_ref="games:thing", name="Typed T"),),
    )
    world = _world(make_world, typed)
    await _install(world, "games")
    for node in await world.graph_repos.nodes.list(after=None, limit=50):
        await world.graph.remove(EntityKind.ITEM, node.id)
    games = await _installation(world, "games")
    (record,) = games.owned(EntityKind.ITEM_TYPE)
    await world.graph.remove(EntityKind.ITEM_TYPE, record.entity_id)

    with pytest.raises(
        RequirementsNotMetError, match=r"^Games no longer has Games thing\.$"
    ):
        await _install(world, "typed")


async def test_base_removal_is_blocked_by_every_dependant(
    make_world: MakeWorld,
) -> None:
    """All installed add-ons are named, nothing is touched, and removal unblocks."""
    world = _world(make_world)
    for pack_id in ("games", "music", "extras", "tie"):
        await _install(world, pack_id)
    before = await _snapshot(world)

    with pytest.raises(RequiredByInstalledPackError) as blocked:
        await _uninstall(world, "games")

    assert str(blocked.value) == "Remove Extras and Tie first."
    assert blocked.value.names == ("Extras", "Tie")
    assert await _snapshot(world) == before
    assert (await _installation(world, "games")).status is InstallationStatus.INSTALLED
    assert world.collections.events == []

    await _uninstall(world, "extras")
    with pytest.raises(RequiredByInstalledPackError, match=r"Remove Tie first\."):
        await _uninstall(world, "games")
    await _uninstall(world, "tie")
    result = await _uninstall(world, "games")

    assert result.kept == ()
    assert await _names(world) == ["Music A", "Music B"]


async def test_a_half_installed_add_on_also_blocks_removal(
    make_world: MakeWorld,
) -> None:
    """An unfinished installation of a dependant still needs the base."""
    world = _world(make_world)
    await _install(world, "games")
    await world.installations.add(Installation.start("extras"))

    with pytest.raises(RequiredByInstalledPackError, match=r"Remove Extras first\."):
        await _uninstall(world, "games")


async def test_removing_the_add_on_leaves_the_base_untouched(
    make_world: MakeWorld,
) -> None:
    """Its connections to base items go with it; base entities all remain."""
    world = _world(make_world)
    await _install(world, "games")
    await _install(world, "extras")

    result = await _uninstall(world, "extras")

    assert result.kept == ()
    assert result.removed.connections == 2
    assert await _names(world) == ["Games A", "Games B"]
    assert await _edge_pairs(world) == {("Games A", "Games B")}
    assert world.collections.collections == {}
    games = await _installation(world, "games")
    assert all(r.outcome is Outcome.OWNED for r in games.entities)
    assert len(await world.graph_repos.node_types.list(after=None, limit=50)) == 1


async def test_a_kept_add_on_connection_keeps_the_base_item(
    make_world: MakeWorld,
) -> None:
    """An edited connection survives the add-on, so the base item has user data."""
    world = _world(make_world)
    await _install(world, "games")
    await _install(world, "extras")
    a = await _node(world, "Games A")
    edges = await world.graph_repos.edges.list(after=None, limit=50)
    edge = next(e for e in edges if e.target_id == a.id)
    edge.attributes = {"note": "mine"}
    await world.graph_repos.edges.save(edge)

    removed = await _uninstall(world, "extras")
    assert (EntityKind.CONNECTION, KEEP_EDITED) in {
        (k.kind, k.reason) for k in removed.kept
    }
    base = await _uninstall(world, "games")

    assert {(k.kind, k.label, k.reason) for k in base.kept} >= {
        (EntityKind.ITEM, "Games A", KEEP_USER_DATA)
    }
    assert "Games A" in await _names(world)
    assert "Games B" not in await _names(world)


async def test_a_failed_add_on_install_leaves_the_base_intact(
    make_world: MakeWorld,
) -> None:
    """A late failure rolls back only the add-on's own entities."""
    world = _world(make_world)
    await _install(world, "games")
    before = await _snapshot(world)
    base_entities = list((await _installation(world, "games")).entities)
    world.collections.fail_on_call = 1

    with pytest.raises(InstallFailedError, match="Nothing was left behind"):
        await _install(world, "extras")

    assert await _snapshot(world) == before
    games = await _installation(world, "games")
    assert games.status is InstallationStatus.INSTALLED
    assert list(games.entities) == base_entities
    (failed,) = await world.installations.list_for_pack("extras")
    assert failed.status is InstallationStatus.FAILED
    assert (await _uninstall(world, "games")).kept == ()


async def test_an_add_ons_kept_entities_are_adopted_on_reinstall(
    make_world: MakeWorld,
) -> None:
    """Kept add-on entities, including a connection to a base item, come back."""
    world = _world(make_world)
    await _install(world, "games")
    await _install(world, "extras")
    x = await _node(world, "Extra X")
    x.name = "Mine"
    await world.graph_repos.nodes.save(x)
    a = await _node(world, "Games A")
    edges = await world.graph_repos.edges.list(after=None, limit=50)
    edge = next(e for e in edges if e.target_id == a.id)
    edge.attributes = {"note": "mine"}
    await world.graph_repos.edges.save(edge)
    removed = await _uninstall(world, "extras")
    assert {k.kind for k in removed.kept} >= {EntityKind.ITEM, EntityKind.CONNECTION}

    again = await _install(world, "extras")

    assert (again.adopted.items, again.adopted.connections) == (1, 1)
    assert again.adopted.item_types == 1
    assert (again.created.items, again.created.connections) == (1, 1)
    assert await _names(world) == ["Extra Y", "Games A", "Games B", "Mine"]
    assert len(await world.graph_repos.edges.list(after=None, limit=50)) == 3


async def test_ordinary_packs_are_unaffected(make_world: MakeWorld) -> None:
    """A pack with no requirements installs and removes as before."""
    world = _world(make_world)

    result = await _install(world, "games")
    removed = await _uninstall(world, "games")

    assert (result.created.items, result.created.connections) == (2, 1)
    assert (removed.removed.items, removed.kept) == (2, ())


async def test_a_missing_record_is_named_by_its_ref(make_world: MakeWorld) -> None:
    """If the required pack's record never existed, the ref stands in for the label."""
    world = _world(make_world)
    finished = Installation.start("games")
    finished.mark_installed()

    with pytest.raises(RequirementsNotMetError, match=r"Games no longer has a\."):
        await resolve_external_refs(_extras(), [finished], world.graph, world.catalogue)


async def test_dependants_by_pack_lists_active_dependants_in_catalogue_order(
    make_world: MakeWorld,
) -> None:
    """Only active add-ons count; ids outside the catalogue are ignored."""
    world = _world(make_world)
    packs = await world.catalogue.list_packs()

    result = dependants_by_pack(packs, {"extras", "tie", "ghost"})

    assert [s.id for s in result["games"]] == ["extras", "tie"]
    assert [s.id for s in result["music"]] == ["tie"]
    assert "extras" not in result
    assert dependants_by_pack(packs, set()) == {}


async def test_a_failed_dependant_does_not_block_removal(
    make_world: MakeWorld,
) -> None:
    """Only active installations count; failed and removed ones are history."""
    world = _world(make_world)
    await _install(world, "games")
    failed = Installation.start("extras")
    failed.mark_failed()
    await world.installations.add(failed)
    removed = Installation.start("tie")
    removed.mark_removed()
    await world.installations.add(removed)

    assert (await _uninstall(world, "games")).kept == ()


async def test_removal_is_blocked_along_a_chain_of_add_ons(
    make_world: MakeWorld,
) -> None:
    """With a requiring b requiring c, c waits for b and b waits for a."""
    chain = [
        ExamplePack(id="c-pack"),
        ExamplePack(id="b-pack", requires=("c-pack",)),
        ExamplePack(id="a-pack", requires=("b-pack",)),
    ]
    world = make_world(*chain)
    for pack in chain:
        await _install(world, pack.id)

    with pytest.raises(RequiredByInstalledPackError, match=r"Remove B-Pack first\."):
        await _uninstall(world, "c-pack")
    with pytest.raises(RequiredByInstalledPackError, match=r"Remove A-Pack first\."):
        await _uninstall(world, "b-pack")
    for pack_id in ("a-pack", "b-pack", "c-pack"):
        await _uninstall(world, pack_id)

    assert await world.installations.list_active() == []


def _covered_world(make_world: MakeWorld) -> World:
    return make_world(_base("games", cover="box"), _extras())


async def _cover_count(world: World, name: str) -> int:
    node = await _node(world, name)
    return len(
        await world.media_repos.attachments.list_for_target(
            AttachmentTarget.NODE, node.id
        )
    )


async def test_an_add_on_item_of_a_base_cover_type_gets_a_cover(
    make_world: MakeWorld,
) -> None:
    """The cover is the add-on's own; the add-on's other items get none."""
    world = _covered_world(make_world)
    await _install(world, "games")
    base_calls = len(world.covers.create_calls)

    await _install(world, "extras")

    assert [c[1:] for c in world.covers.create_calls[base_calls:]] == [
        ("Extra Y", "box")
    ]
    covers = (await _installation(world, "extras")).owned(EntityKind.COVER)
    assert [(c.ref, c.label) for c in covers] == [("y", "Extra Y")]
    assert len((await _installation(world, "games")).owned(EntityKind.COVER)) == 2


async def test_removing_the_add_on_removes_only_its_cover(
    make_world: MakeWorld,
) -> None:
    """The base's covers are untouched."""
    world = _covered_world(make_world)
    await _install(world, "games")
    await _install(world, "extras")
    removed_before = len(world.covers.removed)

    await _uninstall(world, "extras")

    assert len(world.covers.removed) - removed_before == 1
    assert await _cover_count(world, "Games A") == 1
    assert await _cover_count(world, "Games B") == 1


async def test_a_replaced_add_on_cover_is_readopted(make_world: MakeWorld) -> None:
    """A kept cover of an add-on item comes back with its item on reinstall."""
    world = _covered_world(make_world)
    await _install(world, "games")
    await _install(world, "extras")
    y = await _node(world, "Extra Y")
    for existing in await world.media_repos.attachments.list_for_target(
        AttachmentTarget.NODE, y.id
    ):
        existing.clear_attribute_key()
        await world.media_repos.attachments.update(existing)
    asset = MediaAsset.create(
        filename="mine.png", content_type="image/png", size=3, sha256="0" * 64
    )
    asset.promote()
    await world.media_repos.assets.add(asset)
    await world.media_repos.attachments.add(
        MediaAttachment.for_node(
            asset_id=asset.id, node_id=y.id, attribute_key=AttachmentKey.COVER
        )
    )
    await _uninstall(world, "extras")
    created_before = len(world.covers.create_calls)

    again = await _install(world, "extras")

    assert again.adopted.items == 1
    assert len(world.covers.create_calls) == created_before
    covers = (await _installation(world, "extras")).owned(EntityKind.COVER)
    assert [c.ref for c in covers] == ["y"]


async def test_an_add_on_item_of_a_base_type_without_a_cover_gets_none(
    make_world: MakeWorld,
) -> None:
    """No style on the base type, no cover."""
    world = _world(make_world)
    await _install(world, "games")
    await _install(world, "extras")

    assert world.covers.create_calls == []
