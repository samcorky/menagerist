"""Covers on example items: made on install, removed first, kept when replaced."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
    InstallResult,
    installation_counts,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
    UninstallResult,
)
from app.modules.examples.domain.errors import InstallFailedError
from app.modules.examples.domain.installation import EntityKind, Outcome
from app.modules.examples.domain.pack import ExamplePack, PackCover, PackItem
from app.modules.examples.domain.removal import KEEP_USER_DATA
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    import uuid

    from tests.modules.examples.conftest import MakeWorld, SamplePack, World


def _pack(sample_pack: SamplePack, *, extra: bool = False) -> ExamplePack:
    """Return the sample pack with covers on records, and optionally a second one."""
    pack = sample_pack()
    types = (replace(pack.item_types[0], cover=PackCover(style="sleeve")),)
    items = pack.items
    if extra:
        items = (*items, PackItem(ref="red", type_ref="record", name="Red"))
    return replace(pack, item_types=(*types, pack.item_types[1]), items=items)


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
        world.uow, world.presets, world.graph, world.collections, world.covers
    ).handle(UninstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)


async def _item_id(world: World, name: str) -> uuid.UUID:
    nodes = await world.graph_repos.nodes.list(after=None, limit=10)
    return next(n.id for n in nodes if n.name == name)


async def _attachments(world: World, name: str) -> list[MediaAttachment]:
    return await world.media_repos.attachments.list_for_target(
        AttachmentTarget.NODE, await _item_id(world, name)
    )


async def _assets(world: World) -> list[MediaAsset]:
    return [
        a
        for status in MediaStatus
        for a in await world.media_repos.assets.list_by_status(status=status)
    ]


async def _swap_in_own_cover(world: World, name: str) -> None:
    """The person uploads their own image and makes it the cover."""
    item_id = await _item_id(world, name)
    for existing in await _attachments(world, name):
        existing.clear_attribute_key()
        await world.media_repos.attachments.update(existing)
    asset = MediaAsset.create(
        filename="mine.png", content_type="image/png", size=3, sha256="0" * 64
    )
    asset.promote()
    await world.media_repos.assets.add(asset)
    await world.media_repos.attachments.add(
        MediaAttachment.for_node(
            asset_id=asset.id, node_id=item_id, attribute_key=AttachmentKey.COVER
        )
    )


async def test_only_items_of_a_type_with_a_cover_style_get_one(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Blue (a record) gets a cover set as its cover; Ada (a person) does not."""
    world = make_world(_pack(sample_pack))

    result = await _install(world)

    blue = await _attachments(world, "Blue")
    assert [a.attribute_key for a in blue] == [AttachmentKey.COVER]
    assert await _attachments(world, "Ada") == []
    assert len(await _assets(world)) == 1
    assert [c[1:] for c in world.covers.create_calls] == [("Blue", "sleeve")]
    assert (result.created.items, result.created.item_types) == (2, 2)
    assert world.uow.committed is True


async def test_a_cover_is_recorded_as_owned_against_its_item(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The record carries the item's ref and name, and the cover's own id."""
    world = make_world(_pack(sample_pack))

    await _install(world)

    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    [cover] = installation.owned(EntityKind.COVER)
    assert (cover.ref, cover.label) == ("blue", "Blue")
    assert cover.entity_id == (await _attachments(world, "Blue"))[0].id
    assert installation_counts(installation).items == 2  # covers are not a count


async def test_uninstall_removes_covers_first_and_leaves_no_media(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Cover, then the rest; no asset, attachment or stored file remains."""
    world = make_world(_pack(sample_pack, extra=True))
    await _install(world)
    assert len(world.storage._files) == 2

    result = await _uninstall(world)

    assert result.kept == ()
    assert result.removed.items == 3
    assert world.collections.events[0] == "cover"
    assert world.collections.events.index("item") > 1
    assert await _assets(world) == []
    assert world.storage._files == {}
    assert world.storage._thumbnails == {}
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []


async def test_a_cover_the_person_deleted_does_not_block_removal(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A deleted cover settles as gone; the item is then removed as usual."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    [cover] = await _attachments(world, "Blue")
    await world.media_repos.attachments.delete(cover.id)

    result = await _uninstall(world)

    assert result.kept == ()
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []


async def test_a_replaced_cover_is_kept_and_so_is_its_item(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The person's image stays with the item; nothing says 'cover'."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    await _swap_in_own_cover(world, "Blue")

    result = await _uninstall(world)

    assert (EntityKind.ITEM, "Blue", KEEP_USER_DATA) in {
        (k.kind, k.label, k.reason) for k in result.kept
    }
    assert all(k.kind is not EntityKind.COVER for k in result.kept)
    assert all("cover" not in k.reason for k in result.kept)
    assert len(await _attachments(world, "Blue")) == 2
    assert len(await _assets(world)) == 2
    assert [
        n.name for n in await world.graph_repos.nodes.list(after=None, limit=9)
    ] == ["Blue"]


async def test_a_replaced_cover_is_recorded_as_kept_edited(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The cover record is settled as kept, as an edit."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    await _swap_in_own_cover(world, "Blue")

    await _uninstall(world)

    [history] = await world.installations.list_for_pack("demo")
    [cover] = [r for r in history.entities if r.kind is EntityKind.COVER]
    assert (cover.outcome, cover.reason) == (Outcome.KEPT, "edited")
    assert world.covers.removed == []  # kept, so never asked to remove


async def test_a_failure_part_way_removes_the_covers_already_attached(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The second cover fails; the first is removed with everything else."""
    world = make_world(_pack(sample_pack, extra=True))
    world.covers.fail_on_call = 2

    with pytest.raises(InstallFailedError, match="cover boom"):
        await _install(world)

    assert len(world.covers.removed) == 1
    assert await _assets(world) == []
    assert world.storage._files == {}
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []
    assert world.uow.committed is True
    assert await world.installations.get_active_for_pack("demo") is None


async def test_reinstall_readopts_a_kept_cover_without_a_second_one(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Item and cover come back together; the cover keeps its original hash."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    [original] = await _attachments(world, "Blue")
    first = await world.installations.get_active_for_pack("demo")
    assert first is not None
    original_hash = first.owned(EntityKind.COVER)[0].content_hash
    await _swap_in_own_cover(world, "Blue")
    await _uninstall(world)

    result = await _install(world)

    assert (result.adopted.items, result.created.items) == (1, 1)
    assert len(world.covers.create_calls) == 1  # none drawn on the reinstall
    assert len(await _attachments(world, "Blue")) == 2
    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    [cover] = installation.owned(EntityKind.COVER)
    assert (cover.entity_id, cover.content_hash) == (original.id, original_hash)
    again = await _uninstall(world)  # still treated as the person's
    assert EntityKind.ITEM in {k.kind for k in again.kept}
    assert EntityKind.COVER not in {k.kind for k in again.kept}
    assert len(await _attachments(world, "Blue")) == 2


async def test_an_adopted_item_whose_cover_is_gone_gets_a_fresh_one(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Blue is renamed (so kept) and its cover deleted; the reinstall redraws."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    blue = await world.graph_repos.nodes.get(await _item_id(world, "Blue"))
    assert blue is not None
    blue.name = "Mine now"
    await world.graph_repos.nodes.save(blue)
    await _uninstall(world)
    assert await _assets(world) == []

    result = await _install(world)

    assert result.adopted.items == 1
    assert [c[1:] for c in world.covers.create_calls] == [
        ("Blue", "sleeve"),
        ("Mine now", "sleeve"),
    ]
    assert len(await _attachments(world, "Mine now")) == 1


async def test_a_kept_cover_is_not_adopted_without_its_item(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """If the kept item is gone, the cover is not taken back and a new one is drawn."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    await _swap_in_own_cover(world, "Blue")
    await _uninstall(world)
    await world.graph.remove(EntityKind.ITEM, await _item_id(world, "Blue"))

    result = await _install(world)

    assert result.adopted.items == 0
    assert len(world.covers.create_calls) == 2
    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    [cover] = installation.owned(EntityKind.COVER)
    [fresh] = await _attachments(world, "Blue")
    assert (cover.entity_id, fresh.attribute_key) == (fresh.id, AttachmentKey.COVER)


async def _rename(world: World, old: str, new: str) -> None:
    node = await world.graph_repos.nodes.get(await _item_id(world, old))
    assert node is not None
    node.name = new
    await world.graph_repos.nodes.save(node)


async def _covers_of(world: World, name: str) -> list[MediaAttachment]:
    return [
        a
        for a in await _attachments(world, name)
        if a.attribute_key is AttachmentKey.COVER
    ]


async def test_reinstall_never_replaces_a_cover_the_person_set_after_deleting_ours(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Own image swapped in, pack image deleted: the item is kept, its cover stays."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    await _swap_in_own_cover(world, "Blue")
    [theirs] = await _covers_of(world, "Blue")
    [ours] = [a for a in await _attachments(world, "Blue") if a.id != theirs.id]
    await world.media_repos.attachments.delete(ours.id)
    await _uninstall(world)

    await _install(world)

    assert len(world.covers.create_calls) == 1
    assert await _covers_of(world, "Blue") == [theirs]
    installation = await world.installations.get_active_for_pack("demo")
    assert installation is not None
    assert installation.owned(EntityKind.COVER) == []


async def test_reinstall_never_replaces_a_cover_set_after_ours_was_removed(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Item kept for another reason, pack image removed, own image set, reinstall."""
    world = make_world(_pack(sample_pack))
    await _install(world)
    await _rename(world, "Blue", "Mine now")
    await _uninstall(world)
    assert await _attachments(world, "Mine now") == []
    await _swap_in_own_cover(world, "Mine now")
    [theirs] = await _covers_of(world, "Mine now")

    await _install(world)

    assert len(world.covers.create_calls) == 1
    assert await _covers_of(world, "Mine now") == [theirs]


async def test_a_failed_install_leaves_the_persons_cover_flag_alone(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The adopted item is skipped, a later cover fails, and the rollback is safe."""
    world = make_world(_pack(sample_pack, extra=True))
    await _install(world)
    await _rename(world, "Blue", "Mine now")
    await _uninstall(world)
    await _swap_in_own_cover(world, "Mine now")
    [theirs] = await _covers_of(world, "Mine now")
    world.covers.fail_on_call = len(world.covers.create_calls) + 1

    with pytest.raises(InstallFailedError, match="cover boom"):
        await _install(world)

    assert await _covers_of(world, "Mine now") == [theirs]
    assert theirs.id not in world.covers.removed
