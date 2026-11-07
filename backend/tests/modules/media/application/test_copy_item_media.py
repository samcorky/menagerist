import uuid

import pytest

from app.modules.media.adapters.persistence.in_memory_attach_target_access import (
    InMemoryAttachTargetAccess,
)
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.application.copy_item_media import (
    CopyItemMedia,
    CopyItemMediaCommand,
)
from app.modules.media.domain.errors import AttachTargetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter


class _Setup:
    def __init__(self) -> None:
        self.assets = InMemoryMediaAssetRepository()
        self.attachments = InMemoryMediaAttachmentRepository(self.assets)
        self.targets = InMemoryAttachTargetAccess()
        self.storage = InMemoryMediaStorage()
        repos = make_in_memory_repos(assets=self.assets, attachments=self.attachments)
        self.uow = create_in_memory_media_uow(repos)
        self.use_case = CopyItemMedia(
            self.uow, InMemoryAccessGuard(), self.storage, self.targets
        )
        self.source = uuid.uuid7()
        self.target = uuid.uuid7()
        self.targets.add_target(AttachmentTarget.NODE, self.target, SYSTEM_ACTOR.id)

    async def attach(self, *, cover: bool = False, data: bytes = b"jpeg") -> MediaAsset:
        asset = MediaAsset.create(
            owner_id=SYSTEM_ACTOR.id,
            filename="f.jpg",
            content_type="image/jpeg",
            size=len(data),
            sha256="x",
        )
        asset.promote()
        asset.mark_thumbnail_generated(sha256="t")
        await self.assets.add(asset)
        self.storage._files[(asset.id, MediaStatus.ATTACHED.value)] = data
        self.storage._thumbnails[(asset.id, MediaStatus.ATTACHED.value)] = b"thumb"
        await self.attachments.add(
            MediaAttachment.for_node(
                asset_id=asset.id,
                node_id=self.source,
                attribute_key=AttachmentKey.COVER if cover else None,
            )
        )
        return asset

    async def on_target(self) -> list[MediaAttachment]:
        return await self.attachments.list_for_target(
            AttachmentTarget.NODE, self.target, scope=ContentFilter.everyone()
        )


async def _copy(setup: _Setup, *, attachments: bool, cover: bool) -> int:
    return await setup.use_case.handle(
        CopyItemMediaCommand(
            source_id=setup.source,
            target_id=setup.target,
            attachments=attachments,
            cover=cover,
        ),
        SYSTEM_ACTOR,
    )


async def _asset(setup: _Setup, attachment: MediaAttachment) -> MediaAsset:
    asset = await setup.assets.get(attachment.asset_id, scope=ContentFilter.everyone())
    assert asset is not None
    return asset


async def test_attachments_are_copied_without_the_cover() -> None:
    """Copying attachments adds the gallery but not the cover."""
    setup = _Setup()
    photo = await setup.attach()
    await setup.attach(cover=True)

    count = await _copy(setup, attachments=True, cover=False)

    copied = await setup.on_target()
    assert count == 1
    assert [a.attribute_key for a in copied] == [None]
    assert copied[0].asset_id != photo.id


async def test_cover_is_copied_without_the_attachments() -> None:
    """Copying only the cover keeps the cover flag on the target."""
    setup = _Setup()
    await setup.attach()
    cover = await setup.attach(cover=True)

    count = await _copy(setup, attachments=False, cover=True)

    copied = await setup.on_target()
    assert count == 1
    assert [a.attribute_key for a in copied] == [AttachmentKey.COVER]
    assert copied[0].asset_id != cover.id


async def test_every_copy_is_a_separate_asset_with_its_own_file() -> None:
    """The copy has its own asset row, file and thumbnail, with the same details."""
    setup = _Setup()
    photo = await setup.attach(data=b"original bytes")

    await _copy(setup, attachments=True, cover=False)

    copy = await _asset(setup, (await setup.on_target())[0])
    assert copy.id != photo.id
    assert copy.status is MediaStatus.ATTACHED
    assert (copy.filename, copy.content_type, copy.size, copy.sha256) == (
        photo.filename,
        photo.content_type,
        photo.size,
        photo.sha256,
    )
    assert copy.has_thumbnail
    assert copy.thumbnail_sha256 == "t"
    key = MediaStatus.ATTACHED.value
    assert setup.storage._files[(copy.id, key)] == b"original bytes"
    assert setup.storage._thumbnails[(copy.id, key)] == b"thumb"


async def test_deleting_the_copy_leaves_the_original_alone() -> None:
    """Removing the copy's file never touches the original's."""
    setup = _Setup()
    photo = await setup.attach()
    await _copy(setup, attachments=True, cover=False)
    copy = await _asset(setup, (await setup.on_target())[0])

    await setup.storage.delete(copy.id, MediaStatus.ATTACHED)
    await setup.assets.delete(copy.id)

    key = MediaStatus.ATTACHED.value
    assert (photo.id, key) in setup.storage._files
    original = await setup.attachments.list_for_target(
        AttachmentTarget.NODE, setup.source, scope=ContentFilter.everyone()
    )
    assert len(original) == 1


async def test_one_file_used_twice_is_copied_once() -> None:
    """Two attachments of one source asset share one new asset on the target."""
    setup = _Setup()
    photo = await setup.attach()
    await setup.attachments.add(
        MediaAttachment.for_node(
            asset_id=photo.id, node_id=setup.source, attribute_key=AttachmentKey.COVER
        )
    )

    count = await _copy(setup, attachments=True, cover=True)

    copied = await setup.on_target()
    assert count == 2
    assert len({a.asset_id for a in copied}) == 1
    assert len(setup.storage._files) == 2


async def test_neither_choice_copies_nothing() -> None:
    """With both off the target stays bare and nothing is committed."""
    setup = _Setup()
    await setup.attach()

    assert await _copy(setup, attachments=False, cover=False) == 0
    assert await setup.on_target() == []
    assert len(setup.storage._files) == 1


async def test_a_source_file_that_is_not_attached_is_skipped() -> None:
    """An orphaned asset has no file in the attached bucket, so it is left out."""
    setup = _Setup()
    photo = await setup.attach()
    photo.orphan()
    await setup.assets.save(photo)

    assert await _copy(setup, attachments=True, cover=True) == 0
    assert await setup.on_target() == []


async def test_a_failed_commit_removes_the_files_it_copied() -> None:
    """If the rows cannot be saved, no stray copies are left in storage."""
    setup = _Setup()
    await setup.attach()

    async def fail() -> None:
        raise RuntimeError("database gone")

    setup.uow.commit = fail  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await _copy(setup, attachments=True, cover=False)

    assert len(setup.storage._files) == 1


async def test_unknown_target_is_refused() -> None:
    """A target the caller cannot see is a not-found error."""
    setup = _Setup()
    await setup.attach()

    with pytest.raises(AttachTargetNotFoundError):
        await setup.use_case.handle(
            CopyItemMediaCommand(
                source_id=setup.source,
                target_id=uuid.uuid7(),
                attachments=True,
                cover=True,
            ),
            SYSTEM_ACTOR,
        )
    assert len(setup.storage._files) == 1
