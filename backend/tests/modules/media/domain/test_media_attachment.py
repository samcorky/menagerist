import uuid

from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)


def test_for_node_creates_attachment_targeting_node() -> None:
    """for_node is a convenience factory that sets target_type to NODE."""
    asset_id = uuid.uuid4()
    node_id = uuid.uuid4()

    attachment = MediaAttachment.for_node(asset_id=asset_id, node_id=node_id)

    assert attachment.asset_id == asset_id
    assert attachment.target_type is AttachmentTarget.NODE
    assert attachment.target_id == node_id
    assert attachment.attribute_key is None


def test_for_node_forwards_attribute_key() -> None:
    """for_node passes attribute_key through to the attachment."""
    attachment = MediaAttachment.for_node(
        asset_id=uuid.uuid4(), node_id=uuid.uuid4(), attribute_key=AttachmentKey.COVER
    )
    assert attachment.attribute_key is AttachmentKey.COVER


def test_for_edge_creates_attachment_targeting_edge() -> None:
    """for_edge is a convenience factory that sets target_type to EDGE."""
    asset_id = uuid.uuid4()
    edge_id = uuid.uuid4()

    attachment = MediaAttachment.for_edge(asset_id=asset_id, edge_id=edge_id)

    assert attachment.asset_id == asset_id
    assert attachment.target_type is AttachmentTarget.EDGE
    assert attachment.target_id == edge_id
    assert attachment.attribute_key is None


def test_mark_as_cover_sets_attribute_key_and_touches() -> None:
    """mark_as_cover flags the attachment as cover and bumps updated_at."""
    attachment = MediaAttachment.for_node(asset_id=uuid.uuid4(), node_id=uuid.uuid4())
    previous_updated_at = attachment.updated_at

    attachment.mark_as_cover()

    assert attachment.attribute_key is AttachmentKey.COVER
    assert attachment.updated_at >= previous_updated_at


def test_clear_attribute_key_unsets_slot_and_touches() -> None:
    """clear_attribute_key removes the slot label without affecting other fields."""
    attachment = MediaAttachment.for_node(
        asset_id=uuid.uuid4(), node_id=uuid.uuid4(), attribute_key=AttachmentKey.COVER
    )
    previous_updated_at = attachment.updated_at

    attachment.clear_attribute_key()

    assert attachment.attribute_key is None
    assert attachment.updated_at >= previous_updated_at
