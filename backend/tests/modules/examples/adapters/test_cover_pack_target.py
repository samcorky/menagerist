"""The real cover target over in-memory media storage."""

import hashlib
import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.ports.pack_targets import RemoveResult
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, World


async def _attachments(world: World, item_id: uuid.UUID) -> list[MediaAttachment]:
    return await world.media_repos.attachments.list_for_target(
        AttachmentTarget.NODE, item_id
    )


async def test_create_attaches_the_drawn_image_as_the_items_cover(
    make_world: MakeWorld,
) -> None:
    """One attachment flagged as cover; content describes the bytes drawn."""
    world = make_world()
    item_id = uuid.uuid7()

    created = await world.covers.create(item_id, "Blue", "sleeve")

    [attachment] = await _attachments(world, item_id)
    assert created.entity_id == attachment.id
    assert attachment.attribute_key is AttachmentKey.COVER
    asset = await world.media_repos.assets.get(attachment.asset_id)
    assert asset is not None
    assert (asset.content_type, asset.status) == ("image/png", MediaStatus.ATTACHED)
    png = world.covers._renderer.render("Blue", "sleeve")
    assert created.content == {
        "style": "sleeve",
        "name": "Blue",
        "sha256": hashlib.sha256(png).hexdigest(),
    }
    assert asset.sha256 == created.content["sha256"]


async def test_create_is_deterministic_for_the_same_name(make_world: MakeWorld) -> None:
    """A reinstall draws byte-identical covers."""
    world = make_world()

    first = await world.covers.create(uuid.uuid7(), "Blue", "poster")
    second = await world.covers.create(uuid.uuid7(), "Blue", "poster")
    other = await world.covers.create(uuid.uuid7(), "Red", "poster")

    assert first.content == second.content
    assert first.content["sha256"] != other.content["sha256"]


async def test_inspect_matches_what_was_created(make_world: MakeWorld) -> None:
    """Nothing changed, so the hashes agree and nothing counts as user data."""
    world = make_world()
    created = await world.covers.create(uuid.uuid7(), "Ünï", "card")

    inspection = await world.covers.inspect(created.entity_id)

    assert inspection is not None
    assert content_hash(inspection.content) == content_hash(created.content)
    assert (inspection.has_user_data, inspection.still_in_use) == (False, False)


async def test_inspect_reads_a_demoted_cover_as_changed(make_world: MakeWorld) -> None:
    """Once another image is the cover, the pack's is no longer what it made."""
    world = make_world()
    item_id = uuid.uuid7()
    created = await world.covers.create(item_id, "Blue", "box")
    [attachment] = await _attachments(world, item_id)
    attachment.clear_attribute_key()
    await world.media_repos.attachments.update(attachment)

    inspection = await world.covers.inspect(created.entity_id)

    assert inspection is not None
    assert content_hash(inspection.content) != content_hash(created.content)


async def test_inspect_reads_a_renamed_file_as_changed(make_world: MakeWorld) -> None:
    """A filename that no longer says name and style cannot match."""
    world = make_world()
    item_id = uuid.uuid7()
    created = await world.covers.create(item_id, "Blue", "box")
    [attachment] = await _attachments(world, item_id)
    asset = await world.media_repos.assets.get(attachment.asset_id)
    assert asset is not None
    asset.filename = "holiday.png"
    await world.media_repos.assets.save(asset)

    inspection = await world.covers.inspect(created.entity_id)

    assert inspection is not None
    assert content_hash(inspection.content) != content_hash(created.content)


async def test_inspect_is_none_when_the_attachment_or_asset_is_gone(
    make_world: MakeWorld,
) -> None:
    """No attachment, or an attachment without its asset, is a cover that is gone."""
    world = make_world()
    item_id = uuid.uuid7()
    created = await world.covers.create(item_id, "Blue", "box")
    [attachment] = await _attachments(world, item_id)

    await world.media_repos.assets.delete(attachment.asset_id)
    assert await world.covers.inspect(created.entity_id) is None
    await world.media_repos.attachments.delete(attachment.id)
    assert await world.covers.inspect(created.entity_id) is None


async def test_remove_deletes_attachment_asset_and_stored_files(
    make_world: MakeWorld,
) -> None:
    """Nothing is left behind, thumbnail included."""
    world = make_world()
    item_id = uuid.uuid7()
    created = await world.covers.create(item_id, "Blue", "sleeve")
    assert len(world.storage._thumbnails) == 1

    result = await world.covers.remove(created.entity_id)

    assert result is RemoveResult.REMOVED
    assert await _attachments(world, item_id) == []
    for status in MediaStatus:
        assert await world.media_repos.assets.list_by_status(status=status) == []
    assert world.storage._files == {}
    assert world.storage._thumbnails == {}


async def test_remove_of_a_missing_cover_is_already_gone(make_world: MakeWorld) -> None:
    """Nothing to do, and no error."""
    world = make_world()

    assert await world.covers.remove(uuid.uuid7()) is RemoveResult.ALREADY_GONE


async def test_remove_keeps_an_asset_that_is_attached_elsewhere(
    make_world: MakeWorld,
) -> None:
    """Only the cover's own attachment goes if the asset is shared."""
    world = make_world()
    item_id = uuid.uuid7()
    created = await world.covers.create(item_id, "Blue", "sleeve")
    [attachment] = await _attachments(world, item_id)
    await world.media_repos.attachments.add(
        MediaAttachment.for_node(asset_id=attachment.asset_id, node_id=uuid.uuid7())
    )

    result = await world.covers.remove(created.entity_id)

    assert result is RemoveResult.REMOVED
    asset = await world.media_repos.assets.get(attachment.asset_id)
    assert isinstance(asset, MediaAsset)
    assert asset.status is MediaStatus.ATTACHED


async def test_a_failure_setting_the_cover_leaves_nothing_behind(
    make_world: MakeWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half-made cover is detached and deleted before the error escapes."""
    world = make_world()

    async def boom(attachment: MediaAttachment) -> None:
        raise RuntimeError("cover flag boom")

    monkeypatch.setattr(world.media_repos.attachments, "update", boom)

    with pytest.raises(RuntimeError, match="cover flag boom"):
        await world.covers.create(uuid.uuid7(), "Blue", "sleeve")

    for status in MediaStatus:
        assert await world.media_repos.assets.list_by_status(status=status) == []
    assert world.storage._files == {}


async def test_has_cover_is_true_only_for_an_item_with_a_flagged_cover(
    make_world: MakeWorld,
) -> None:
    """Any image flagged as cover counts; an unflagged attachment does not."""
    world = make_world()
    item_id = uuid.uuid7()
    assert await world.covers.has_cover(item_id) is False

    await world.covers.create(item_id, "Blue", "box")
    assert await world.covers.has_cover(item_id) is True

    [attachment] = await _attachments(world, item_id)
    attachment.clear_attribute_key()
    await world.media_repos.attachments.update(attachment)
    assert await world.covers.has_cover(item_id) is False
