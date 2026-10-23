import uuid
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.application.purge_attachment import (
    PurgeAttachment,
    PurgeAttachmentCommand,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import MediaAttachment
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.modules.media.ports.unit_of_work import MediaRepos

OWNER = uuid.UUID(int=1)


async def _asset(repos: MediaRepos, storage: InMemoryMediaStorage) -> MediaAsset:
    asset = MediaAsset.create(
        owner_id=OWNER, filename="a.png", content_type="image/png", size=1, sha256="x"
    )
    asset.promote()
    await repos.assets.add(asset)
    storage._files[(asset.id, MediaStatus.ATTACHED.value)] = b"data"
    return asset


async def _attach(repos: MediaRepos, asset: MediaAsset) -> MediaAttachment:
    attachment = MediaAttachment.for_node(asset_id=asset.id, node_id=uuid.uuid7())
    await repos.attachments.add(attachment)
    return attachment


def _build() -> tuple[MediaRepos, InMemoryMediaStorage, PurgeAttachment]:
    repos, storage = make_in_memory_repos(), InMemoryMediaStorage()
    use_case = PurgeAttachment(
        create_in_memory_media_uow(repos), get_access_guard(), storage
    )
    return repos, storage, use_case


async def test_the_attachment_and_its_only_asset_and_file_go() -> None:
    """Nothing else uses the asset, so the row, the asset and the file are removed."""
    repos, storage, use_case = _build()
    asset = await _asset(repos, storage)
    attachment = await _attach(repos, asset)

    await use_case.handle(
        PurgeAttachmentCommand(attachment_id=attachment.id), SYSTEM_ACTOR
    )

    everyone = ContentFilter.everyone()
    assert await repos.attachments.get(attachment.id, scope=everyone) is None
    assert await repos.assets.get(asset.id, scope=everyone) is None
    assert storage._files == {}


async def test_an_asset_still_attached_elsewhere_survives() -> None:
    """Only the one attachment goes when another still uses the asset."""
    repos, storage, use_case = _build()
    asset = await _asset(repos, storage)
    purged, kept = await _attach(repos, asset), await _attach(repos, asset)

    await use_case.handle(PurgeAttachmentCommand(attachment_id=purged.id), SYSTEM_ACTOR)

    everyone = ContentFilter.everyone()
    assert await repos.attachments.get(purged.id, scope=everyone) is None
    assert await repos.attachments.get(kept.id, scope=everyone) is kept
    assert await repos.assets.get(asset.id, scope=everyone) is asset
    assert (asset.id, MediaStatus.ATTACHED.value) in storage._files


async def test_the_file_is_deleted_only_after_the_commit() -> None:
    """A failed commit must not lose the stored file."""
    repos, storage = make_in_memory_repos(), InMemoryMediaStorage()
    uow = InMemoryUnitOfWork(repos)
    seen: list[bool] = []
    original = storage.delete

    async def spy(asset_id: uuid.UUID, status: MediaStatus) -> None:
        seen.append(uow.committed)
        await original(asset_id, status)

    storage.delete = spy  # type: ignore[method-assign]
    asset = await _asset(repos, storage)
    attachment = await _attach(repos, asset)

    await PurgeAttachment(uow, get_access_guard(), storage).handle(
        PurgeAttachmentCommand(attachment_id=attachment.id), SYSTEM_ACTOR
    )

    assert seen == [True]


async def test_an_unknown_attachment_is_a_no_op() -> None:
    """An id that is already gone changes nothing and does not raise."""
    repos, storage, use_case = _build()
    asset = await _asset(repos, storage)

    await use_case.handle(
        PurgeAttachmentCommand(attachment_id=uuid.uuid7()), SYSTEM_ACTOR
    )

    assert await repos.assets.get(asset.id, scope=ContentFilter.everyone()) is asset
    assert len(storage._files) == 1
