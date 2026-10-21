"""Scoped `MediaAssetRepository` and `MediaAttachmentRepository`, both adapters."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.adapters.persistence.media_attachment_repository import (
    SqlAlchemyMediaAttachmentRepository,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import AttachmentTarget, MediaAttachment
from app.modules.media.ports.media_asset_repository import MediaAssetRepository
from app.modules.media.ports.media_attachment_repository import (
    MediaAttachmentRepository,
)
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = ContentFilter.of(ALICE)
B = ContentFilter.of(BOB)
ALL = ContentFilter.everyone()
STAGED = MediaStatus.STAGED


@dataclass
class Repos:
    """Both repositories of one adapter."""

    assets: MediaAssetRepository
    attachments: MediaAttachmentRepository


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repos(request: pytest.FixtureRequest) -> Repos:
    """The same scenarios run against both adapters."""
    if request.param == "in_memory":
        assets = InMemoryMediaAssetRepository()
        return Repos(assets, InMemoryMediaAttachmentRepository(assets))
    session = request.getfixturevalue("db_session")
    return Repos(
        SqlAlchemyMediaAssetRepository(session),
        SqlAlchemyMediaAttachmentRepository(session),
    )


def _asset(owner: uuid.UUID) -> MediaAsset:
    return MediaAsset.create(
        owner_id=owner,
        filename="f.png",
        content_type="image/png",
        size=1,
        sha256="abc",
    )


async def test_get_hides_other_owners(repos: Repos) -> None:
    """A's asset is visible to A and everyone(), never to B."""
    asset = _asset(ALICE)
    await repos.assets.add(asset)

    assert await repos.assets.get(asset.id, scope=A) is not None
    assert await repos.assets.get(asset.id, scope=ALL) is not None
    assert await repos.assets.get(asset.id, scope=B) is None


async def test_owner_round_trips(repos: Repos) -> None:
    """The stored asset carries its owner."""
    asset = _asset(ALICE)
    await repos.assets.add(asset)

    stored = await repos.assets.get(asset.id, scope=A)
    assert stored is not None
    assert stored.owner_id == ALICE


async def test_list_by_status_is_scoped(repos: Repos) -> None:
    """Each scope lists only its own assets; everyone() lists all."""
    mine, theirs = _asset(ALICE), _asset(BOB)
    await repos.assets.add(mine)
    await repos.assets.add(theirs)

    listed_a = await repos.assets.list_by_status(status=STAGED, scope=A)
    listed_b = await repos.assets.list_by_status(status=STAGED, scope=B)
    listed_all = await repos.assets.list_by_status(status=STAGED, scope=ALL)
    assert [a.id for a in listed_a] == [mine.id]
    assert [a.id for a in listed_b] == [theirs.id]
    assert {a.id for a in listed_all} == {mine.id, theirs.id}


async def test_list_by_status_filters_status(repos: Repos) -> None:
    """The status filter still applies inside a scope."""
    await repos.assets.add(_asset(ALICE))

    attached = await repos.assets.list_by_status(status=MediaStatus.ATTACHED, scope=A)
    assert attached == []


async def test_list_expired_is_scoped(repos: Repos) -> None:
    """Expiry listing honours the scope; the cleanup job passes everyone()."""
    mine, theirs = _asset(ALICE), _asset(BOB)
    await repos.assets.add(mine)
    await repos.assets.add(theirs)
    later = datetime.now(UTC) + timedelta(hours=1)
    earlier = datetime.now(UTC) - timedelta(hours=1)

    expired_a = await repos.assets.list_expired(status=STAGED, before=later, scope=A)
    expired_b = await repos.assets.list_expired(status=STAGED, before=later, scope=B)
    expired_all = await repos.assets.list_expired(
        status=STAGED, before=later, scope=ALL
    )
    not_yet = await repos.assets.list_expired(status=STAGED, before=earlier, scope=ALL)

    assert [a.id for a in expired_a] == [mine.id]
    assert [a.id for a in expired_b] == [theirs.id]
    assert {a.id for a in expired_all} == {mine.id, theirs.id}
    assert not_yet == []


async def test_attachments_follow_their_asset(repos: Repos) -> None:
    """B sees none of A's attachments by target, asset or id."""
    asset = _asset(ALICE)
    await repos.assets.add(asset)
    node_id = uuid.uuid7()
    attachment = MediaAttachment.for_node(asset_id=asset.id, node_id=node_id)
    await repos.attachments.add(attachment)

    for scope in (A, ALL):
        by_target = await repos.attachments.list_for_target(
            AttachmentTarget.NODE, node_id, scope=scope
        )
        assert [x.id for x in by_target] == [attachment.id]
        by_asset = await repos.attachments.list_for_asset(asset.id, scope=scope)
        assert [x.id for x in by_asset] == [attachment.id]
        assert await repos.attachments.get(attachment.id, scope=scope) is not None
    hidden = await repos.attachments.list_for_target(
        AttachmentTarget.NODE, node_id, scope=B
    )
    assert hidden == []
    assert await repos.attachments.list_for_asset(asset.id, scope=B) == []
    assert await repos.attachments.get(attachment.id, scope=B) is None


async def test_attachments_only_include_the_scopes_assets(repos: Repos) -> None:
    """Two owners' attachments on one target are split by scope."""
    mine, theirs = _asset(ALICE), _asset(BOB)
    await repos.assets.add(mine)
    await repos.assets.add(theirs)
    node_id = uuid.uuid7()
    first = MediaAttachment.for_node(asset_id=mine.id, node_id=node_id)
    second = MediaAttachment.for_node(asset_id=theirs.id, node_id=node_id)
    await repos.attachments.add(first)
    await repos.attachments.add(second)

    on_target_a = await repos.attachments.list_for_target(
        AttachmentTarget.NODE, node_id, scope=A
    )
    on_target_all = await repos.attachments.list_for_target(
        AttachmentTarget.NODE, node_id, scope=ALL
    )
    assert [x.id for x in on_target_a] == [first.id]
    assert {x.id for x in on_target_all} == {first.id, second.id}


@pytest.mark.integration
async def test_null_owner_is_invisible_to_a_person(db_session: AsyncSession) -> None:
    """Legacy rows with no owner match only everyone()."""
    assets = SqlAlchemyMediaAssetRepository(db_session)
    attachments = SqlAlchemyMediaAttachmentRepository(db_session)
    asset = _asset(ALICE)
    await assets.add(asset)
    node_id = uuid.uuid7()
    await attachments.add(MediaAttachment.for_node(asset_id=asset.id, node_id=node_id))
    await db_session.execute(
        text("UPDATE media_assets SET owner_id = NULL WHERE id = :id"), {"id": asset.id}
    )
    db_session.expire_all()

    assert await assets.get(asset.id, scope=A) is None
    assert await assets.get(asset.id, scope=ALL) is not None
    assert await assets.list_by_status(status=STAGED, scope=A) == []
    hidden = await attachments.list_for_target(AttachmentTarget.NODE, node_id, scope=A)
    assert hidden == []
    assert len(await attachments.list_for_asset(asset.id, scope=ALL)) == 1
