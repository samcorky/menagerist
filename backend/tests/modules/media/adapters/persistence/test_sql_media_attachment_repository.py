import asyncio
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.adapters.persistence.media_attachment_repository import (
    SqlAlchemyMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import create_media_uow
from app.modules.media.application.set_media_cover import (
    SetMediaCover,
    SetMediaCoverCommand,
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

from app.shared_kernel.actor import SYSTEM_ACTOR

pytestmark = pytest.mark.integration

_RACE_ROUNDS = 20


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


async def test_concurrent_set_cover_calls_serialise_to_one_cover(
    postgres_url: str,
) -> None:
    """Two simultaneous set-cover calls on one item both succeed; one cover remains."""
    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for _ in range(_RACE_ROUNDS):
            node_id = uuid.uuid7()
            async with factory() as session:
                assets = [await _asset(session), await _asset(session)]
                for asset in assets:
                    await SqlAlchemyMediaAttachmentRepository(session).add(
                        MediaAttachment.for_node(asset_id=asset.id, node_id=node_id)
                    )
                await session.commit()

            async def set_cover(
                asset_id: uuid.UUID, node_id: uuid.UUID = node_id
            ) -> None:
                await SetMediaCover(create_media_uow(factory)).handle(
                    SetMediaCoverCommand(
                        asset_id=asset_id,
                        target_type=AttachmentTarget.NODE,
                        target_id=node_id,
                    ),
                    SYSTEM_ACTOR,
                )

            await asyncio.gather(*(set_cover(a.id) for a in assets))

            async with factory() as session:
                stored = await SqlAlchemyMediaAttachmentRepository(
                    session
                ).list_for_target(AttachmentTarget.NODE, node_id)
            covers = [a for a in stored if a.attribute_key is AttachmentKey.COVER]
            assert len(stored) == 2
            assert len(covers) == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM media_attachments"))
            await connection.execute(text("DELETE FROM media_assets"))
        await engine.dispose()
