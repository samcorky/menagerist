"""Media use cases with two people: nothing crosses owners, nothing is written."""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.media.adapters.imaging.in_memory_image_processor import (
    InMemoryImageProcessor,
)
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
from app.modules.media.adapters.policy.content_type_attachment_policy import (
    ContentTypeAttachmentPolicy,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.application.attach_media import AttachMedia, AttachMediaCommand
from app.modules.media.application.clear_media_cover import (
    ClearMediaCover,
    ClearMediaCoverCommand,
)
from app.modules.media.application.delete_media import DeleteMedia, DeleteMediaCommand
from app.modules.media.application.detach_media import DetachMedia, DetachMediaCommand
from app.modules.media.application.get_media import GetMedia, GetMediaQuery
from app.modules.media.application.list_node_media import (
    ListNodeMedia,
    ListNodeMediaQuery,
)
from app.modules.media.application.orphan_media import OrphanMedia, OrphanMediaCommand
from app.modules.media.application.promote_media import (
    PromoteMedia,
    PromoteMediaCommand,
)
from app.modules.media.application.set_media_cover import (
    SetMediaCover,
    SetMediaCoverCommand,
)
from app.modules.media.application.stage_media import StageMedia, StageMediaCommand
from app.modules.media.application.update_media import UpdateMedia, UpdateMediaCommand
from app.modules.media.application.upload_and_attach_media import (
    UploadAndAttachMedia,
    UploadAndAttachMediaCommand,
)
from app.modules.media.domain.errors import (
    AttachTargetNotFoundError,
    MediaAssetNotFoundError,
    MediaAttachmentNotFoundError,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.modules.media.ports.unit_of_work import MediaRepos, MediaUnitOfWork
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import NotFoundError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
POLICY = OwnerAccessPolicy()
NODE = AttachmentTarget.NODE


@dataclass
class World:
    """In-memory media with a write spy on the unit of work."""

    repos: MediaRepos
    assets: InMemoryMediaAssetRepository
    attachments: InMemoryMediaAttachmentRepository
    uow: MediaUnitOfWork
    storage: InMemoryMediaStorage
    targets: InMemoryAttachTargetAccess
    writes: list[str]


@pytest.fixture
def world() -> World:
    """A fresh world; every repository write is recorded in `writes`."""
    assets = InMemoryMediaAssetRepository()
    attachments = InMemoryMediaAttachmentRepository(assets)
    writes: list[str] = []
    for repo, names in (
        (assets, ("add", "save", "delete")),
        (attachments, ("add", "update", "delete")),
    ):
        for name in names:
            original = getattr(repo, name)

            async def spy(
                *args: object,
                _original: object = original,
                _label: str = f"{type(repo).__name__}.{name}",
                **kwargs: object,
            ) -> None:
                writes.append(_label)
                await _original(*args, **kwargs)  # type: ignore[operator]

            setattr(repo, name, spy)
    repos = make_in_memory_repos(assets=assets, attachments=attachments)
    return World(
        repos=repos,
        assets=assets,
        attachments=attachments,
        uow=create_in_memory_media_uow(repos),
        storage=InMemoryMediaStorage(),
        targets=InMemoryAttachTargetAccess(),
        writes=writes,
    )


async def _asset(
    world: World, owner: Actor, *, status: MediaStatus = MediaStatus.STAGED
) -> MediaAsset:
    asset = MediaAsset.create(
        owner_id=owner.id,
        filename="f.png",
        content_type="image/png",
        size=1,
        sha256="x",
    )
    if status is not MediaStatus.STAGED:
        asset.promote()
    if status is MediaStatus.ORPHANED:
        asset.orphan()
    await world.assets.add(asset)
    await world.storage.store(asset.id, status, _stream(b"x"))
    world.writes.clear()
    return asset


async def _stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _attach_use_case(world: World) -> AttachMedia:
    return AttachMedia(
        world.uow,
        POLICY,
        world.storage,
        ContentTypeAttachmentPolicy(),
        world.targets,
    )


def _no_writes(world: World) -> None:
    assert world.writes == []
    assert not world.uow.committed  # type: ignore[attr-defined]


# ── Staging ────────────────────────────────────────────────────────────────────


async def test_staged_uploads_belong_to_the_uploader(world: World) -> None:
    """The actor becomes the owner of what they stage."""
    use_case = StageMedia(world.uow, world.storage, InMemoryImageProcessor())

    asset = await use_case.handle(
        StageMediaCommand(
            filename="a.png", content_type="image/png", stream=_stream(b"abc")
        ),
        ALICE,
    )

    assert asset.owner_id == ALICE.id
    assert await world.assets.get(asset.id, scope=AccessScope.of(BOB.id)) is None


# ── Single asset reads and writes ──────────────────────────────────────────────


async def test_get_is_not_found_for_another_owner(world: World) -> None:
    """B gets the same error as for a missing id; A and the system get the asset."""
    asset = await _asset(world, ALICE)
    use_case = GetMedia(world.repos, POLICY)

    for actor in (ALICE, SYSTEM_ACTOR):
        found = await use_case.handle(GetMediaQuery(asset_id=asset.id), actor)
        assert found is asset
    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(GetMediaQuery(asset_id=asset.id), BOB)


async def test_update_by_another_owner_changes_nothing(world: World) -> None:
    """B cannot rename A's asset."""
    asset = await _asset(world, ALICE)
    use_case = UpdateMedia(world.uow, POLICY)

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(UpdateMediaCommand(asset_id=asset.id, filename="x"), BOB)

    _no_writes(world)
    assert asset.filename == "f.png"


async def test_delete_by_another_owner_removes_nothing(world: World) -> None:
    """B cannot delete A's asset or its file."""
    asset = await _asset(world, ALICE)
    use_case = DeleteMedia(world.uow, POLICY, world.storage)

    with pytest.raises(MediaAssetNotFoundError):
        await use_case.handle(DeleteMediaCommand(asset_id=asset.id), BOB)

    _no_writes(world)
    assert (asset.id, "staged") in world.storage._files


async def test_owner_can_delete_their_asset(world: World) -> None:
    """The owner's delete removes the record and the file."""
    asset = await _asset(world, ALICE)

    await DeleteMedia(world.uow, POLICY, world.storage).handle(
        DeleteMediaCommand(asset_id=asset.id), ALICE
    )

    assert await world.assets.get(asset.id, scope=AccessScope.everyone()) is None
    assert (asset.id, "staged") not in world.storage._files


async def test_promote_by_another_owner_changes_nothing(world: World) -> None:
    """B cannot promote A's staged asset."""
    asset = await _asset(world, ALICE)

    with pytest.raises(MediaAssetNotFoundError):
        await PromoteMedia(world.uow, POLICY, world.storage).handle(
            PromoteMediaCommand(asset_id=asset.id), BOB
        )

    _no_writes(world)
    assert asset.status is MediaStatus.STAGED


async def test_orphan_by_another_owner_changes_nothing(world: World) -> None:
    """B cannot orphan A's attached asset."""
    asset = await _asset(world, ALICE, status=MediaStatus.ATTACHED)

    with pytest.raises(MediaAssetNotFoundError):
        await OrphanMedia(world.uow, POLICY, world.storage).handle(
            OrphanMediaCommand(asset_id=asset.id), BOB
        )

    _no_writes(world)
    assert asset.status is MediaStatus.ATTACHED


# ── Attaching ──────────────────────────────────────────────────────────────────


async def test_attach_needs_the_asset_to_be_the_actors(world: World) -> None:
    """B cannot attach A's asset, even to B's own item."""
    asset = await _asset(world, ALICE)
    item = uuid.uuid7()
    world.targets.add_target(NODE, item, BOB.id)

    with pytest.raises(MediaAssetNotFoundError):
        await _attach_use_case(world).handle(
            AttachMediaCommand(asset_id=asset.id, target_type=NODE, target_id=item),
            BOB,
        )

    _no_writes(world)
    assert asset.status is MediaStatus.STAGED


async def test_attach_needs_the_target_to_be_visible(world: World) -> None:
    """A cannot attach A's asset to B's item, or to one that does not exist."""
    asset = await _asset(world, ALICE)
    theirs = uuid.uuid7()
    world.targets.add_target(NODE, theirs, BOB.id)

    for target_id in (theirs, uuid.uuid7()):
        with pytest.raises(AttachTargetNotFoundError):
            await _attach_use_case(world).handle(
                AttachMediaCommand(
                    asset_id=asset.id, target_type=NODE, target_id=target_id
                ),
                ALICE,
            )

    _no_writes(world)
    assert asset.status is MediaStatus.STAGED
    assert (asset.id, "staged") in world.storage._files


async def test_attach_to_own_item_works(world: World) -> None:
    """An owner attaches their own asset to their own item."""
    asset = await _asset(world, ALICE)
    item = uuid.uuid7()
    world.targets.add_target(NODE, item, ALICE.id)

    attachment = await _attach_use_case(world).handle(
        AttachMediaCommand(asset_id=asset.id, target_type=NODE, target_id=item), ALICE
    )

    assert attachment.target_id == item
    assert asset.status is MediaStatus.ATTACHED


async def test_upload_and_attach_to_a_foreign_item_stores_nothing(
    world: World,
) -> None:
    """The target is refused before any bytes are streamed to storage."""
    theirs = uuid.uuid7()
    world.targets.add_target(NODE, theirs, BOB.id)
    use_case = UploadAndAttachMedia(
        world.uow,
        POLICY,
        world.storage,
        ContentTypeAttachmentPolicy(),
        InMemoryImageProcessor(),
        world.targets,
    )

    with pytest.raises(AttachTargetNotFoundError):
        await use_case.handle(
            UploadAndAttachMediaCommand(
                filename="a.png",
                content_type="image/png",
                stream=_stream(b"abc"),
                target_type=NODE,
                target_id=theirs,
            ),
            ALICE,
        )

    _no_writes(world)
    assert world.storage._files == {}


async def test_upload_and_attach_to_own_item_is_owned_by_the_uploader(
    world: World,
) -> None:
    """The new asset is the uploader's."""
    item = uuid.uuid7()
    world.targets.add_target(NODE, item, ALICE.id)
    use_case = UploadAndAttachMedia(
        world.uow,
        POLICY,
        world.storage,
        ContentTypeAttachmentPolicy(),
        InMemoryImageProcessor(),
        world.targets,
    )

    attachment = await use_case.handle(
        UploadAndAttachMediaCommand(
            filename="a.png",
            content_type="image/png",
            stream=_stream(b"abc"),
            target_type=NODE,
            target_id=item,
        ),
        ALICE,
    )

    asset = await world.assets.get(attachment.asset_id, scope=AccessScope.of(ALICE.id))
    assert asset is not None
    assert asset.owner_id == ALICE.id


# ── Attachments of someone else's asset ────────────────────────────────────────


async def _attached(world: World) -> tuple[MediaAsset, MediaAttachment, uuid.UUID]:
    asset = await _asset(world, ALICE, status=MediaStatus.ATTACHED)
    item = uuid.uuid7()
    attachment = MediaAttachment.for_node(asset_id=asset.id, node_id=item)
    await world.attachments.add(attachment)
    world.writes.clear()
    return asset, attachment, item


async def test_detach_by_another_owner_changes_nothing(world: World) -> None:
    """B cannot detach A's attachment."""
    asset, attachment, item = await _attached(world)

    with pytest.raises(MediaAssetNotFoundError):
        await DetachMedia(world.uow, POLICY, world.storage).handle(
            DetachMediaCommand(asset_id=asset.id, target_type=NODE, target_id=item),
            BOB,
        )

    _no_writes(world)
    assert attachment.id in world.attachments._store
    assert asset.status is MediaStatus.ATTACHED


async def test_set_and_clear_cover_by_another_owner_change_nothing(
    world: World,
) -> None:
    """B cannot move or clear A's cover."""
    asset, attachment, item = await _attached(world)
    attachment.mark_as_cover()

    with pytest.raises(MediaAssetNotFoundError):
        await SetMediaCover(world.uow, POLICY).handle(
            SetMediaCoverCommand(asset_id=asset.id, target_type=NODE, target_id=item),
            BOB,
        )
    with pytest.raises(MediaAssetNotFoundError):
        await ClearMediaCover(world.uow, POLICY).handle(
            ClearMediaCoverCommand(asset_id=asset.id, target_type=NODE, target_id=item),
            BOB,
        )

    _no_writes(world)
    assert attachment.attribute_key is AttachmentKey.COVER


async def test_clear_cover_without_one_is_not_found(world: World) -> None:
    """A cover that is not set is a missing attachment for its owner."""
    asset, _, item = await _attached(world)

    with pytest.raises(MediaAttachmentNotFoundError):
        await ClearMediaCover(world.uow, POLICY).handle(
            ClearMediaCoverCommand(asset_id=asset.id, target_type=NODE, target_id=item),
            ALICE,
        )


async def test_listing_media_for_another_owners_item_is_empty(world: World) -> None:
    """B sees nothing on A's item; A sees the file."""
    _, _, item = await _attached(world)
    use_case = ListNodeMedia(world.repos, POLICY)

    mine = await use_case.handle(ListNodeMediaQuery(node_id=item), ALICE)
    theirs = await use_case.handle(ListNodeMediaQuery(node_id=item), BOB)

    assert len(mine) == 1
    assert theirs == []


def test_not_found_errors_are_404_types() -> None:
    """Foreign media answers with a NotFoundError, never a permission error."""
    assert issubclass(MediaAssetNotFoundError, NotFoundError)
    assert issubclass(AttachTargetNotFoundError, NotFoundError)
