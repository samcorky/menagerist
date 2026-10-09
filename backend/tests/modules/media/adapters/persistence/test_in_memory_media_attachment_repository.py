import uuid

import pytest

from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.domain.errors import CoverAlreadySetError
from app.modules.media.domain.media_attachment import AttachmentKey, MediaAttachment


def _cover(node_id: uuid.UUID) -> MediaAttachment:
    return MediaAttachment.for_node(
        asset_id=uuid.uuid4(), node_id=node_id, attribute_key=AttachmentKey.COVER
    )


async def test_add_rejects_a_second_cover_for_one_target() -> None:
    """The in-memory repository mirrors the one-cover-per-target constraint."""
    repo = InMemoryMediaAttachmentRepository()
    node_id = uuid.uuid4()
    await repo.add(_cover(node_id))

    with pytest.raises(CoverAlreadySetError):
        await repo.add(_cover(node_id))


async def test_add_allows_covers_on_different_targets_and_plain_extras() -> None:
    """Other targets and key-less attachments are unaffected."""
    repo = InMemoryMediaAttachmentRepository()
    node_id = uuid.uuid4()
    await repo.add(_cover(node_id))
    await repo.add(_cover(uuid.uuid4()))
    await repo.add(MediaAttachment.for_node(asset_id=uuid.uuid4(), node_id=node_id))
