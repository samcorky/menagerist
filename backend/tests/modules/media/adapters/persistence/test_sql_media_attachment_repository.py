import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.adapters.persistence.media_attachment_repository import (
    SqlAlchemyMediaAttachmentRepository,
)
from app.modules.media.domain.errors import CoverAlreadySetError
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _asset(session: AsyncSession) -> MediaAsset:
    asset = MediaAsset.create(
        filename="c.png", content_type="image/png", size=1, sha256="c"
    )
    await SqlAlchemyMediaAssetRepository(session).add(asset)
    return asset


async def test_second_cover_for_one_target_raises_cover_already_set(
    db_session: AsyncSession,
) -> None:
    """The real unique index surfaces as the domain error, not an IntegrityError."""
    repo = SqlAlchemyMediaAttachmentRepository(db_session)
    node_id = uuid.uuid7()
    first, second = await _asset(db_session), await _asset(db_session)
    await repo.add(
        MediaAttachment.for_node(
            asset_id=first.id, node_id=node_id, attribute_key=AttachmentKey.COVER
        )
    )

    with pytest.raises(CoverAlreadySetError):
        await repo.add(
            MediaAttachment.for_node(
                asset_id=second.id, node_id=node_id, attribute_key=AttachmentKey.COVER
            )
        )

    # The savepoint leaves the session usable and the first cover intact.
    stored = await repo.list_for_target(AttachmentTarget.NODE, node_id)
    assert [a.asset_id for a in stored] == [first.id]


async def test_other_integrity_errors_are_not_translated(
    db_session: AsyncSession,
) -> None:
    """Only the cover constraint maps to the domain error."""
    repo = SqlAlchemyMediaAttachmentRepository(db_session)

    with pytest.raises(IntegrityError):
        await repo.add(
            MediaAttachment.for_node(asset_id=uuid.uuid7(), node_id=uuid.uuid7())
        )


async def test_covers_on_different_targets_and_plain_attachments_are_allowed(
    db_session: AsyncSession,
) -> None:
    """The constraint is per target and only for the cover key."""
    repo = SqlAlchemyMediaAttachmentRepository(db_session)
    node_id = uuid.uuid7()
    asset = await _asset(db_session)
    await repo.add(
        MediaAttachment.for_node(
            asset_id=asset.id, node_id=node_id, attribute_key=AttachmentKey.COVER
        )
    )
    await repo.add(
        MediaAttachment.for_node(
            asset_id=asset.id, node_id=uuid.uuid7(), attribute_key=AttachmentKey.COVER
        )
    )
    await repo.add(MediaAttachment.for_node(asset_id=asset.id, node_id=node_id))
