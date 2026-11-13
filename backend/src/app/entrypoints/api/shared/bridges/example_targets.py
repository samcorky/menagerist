"""Adapter that lets the examples module draw and attach generated covers."""

import hashlib
import re
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.attach_target_access import (
    GraphAttachTargetAccess,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.examples.adapters.covers.pillow_cover_renderer import (
    PillowCoverRenderer,
)
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.media.adapters.api.dependencies import (
    get_attachment_policy,
    get_image_processor,
    get_media_storage,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    build_media_repos,
    create_in_memory_media_uow,
    create_media_uow,
)
from app.modules.media.application.purge_attachment import (
    PurgeAttachment,
    PurgeAttachmentCommand,
)
from app.modules.media.application.set_media_cover import (
    SetMediaCover,
    SetMediaCoverCommand,
)
from app.modules.media.application.upload_and_attach_media import (
    UploadAndAttachMedia,
    UploadAndAttachMediaCommand,
)
from app.modules.media.domain.media_attachment import AttachmentKey, AttachmentTarget
from app.modules.media.ports.attach_target_access import AttachTargetAccess
from app.modules.media.ports.attachment_policy import AttachmentPolicyPort  # noqa: TC001
from app.modules.media.ports.image_processor import ImageProcessorPort  # noqa: TC001
from app.modules.media.ports.media_storage import MediaStoragePort  # noqa: TC001
from app.modules.media.ports.unit_of_work import MediaRepos, MediaUnitOfWork
from app.modules.transfer.ports.targets import Created, Inspection, RemoveResult
from app.platform.database import get_session_factory
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.examples.ports.cover_renderer import CoverRenderer
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.access_guard import AccessGuard


# ---- stores: how targets reach storage (sessions in production, memory in tests) ----


_COVER_FILENAME = re.compile(r"(?P<name>.*) \((?P<style>[a-z]+)\)\.png", re.DOTALL)


async def _single_chunk(data: bytes) -> AsyncIterator[bytes]:
    yield data


@dataclass(kw_only=True)
@dataclass(kw_only=True)
@dataclass(kw_only=True)
@dataclass(kw_only=True)
class CoverStores:
    """Factories the cover target uses; each call opens fresh storage access."""

    uow: Callable[[], MediaUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[MediaRepos]]
    targets: Callable[[], AbstractAsyncContextManager[AttachTargetAccess]]


def in_memory_cover_stores(
    media_repos: MediaRepos, graph_repos: GraphRepos
) -> CoverStores:
    """Stores over in-memory repositories, for tests."""

    @asynccontextmanager
    async def read() -> AsyncIterator[MediaRepos]:
        yield media_repos

    @asynccontextmanager
    async def targets() -> AsyncIterator[AttachTargetAccess]:
        yield GraphAttachTargetAccess(graph_repos)

    return CoverStores(
        uow=lambda: create_in_memory_media_uow(media_repos),
        read=read,
        targets=targets,
    )


def build_cover_stores(
    session_factory: async_sessionmaker[AsyncSession],
) -> CoverStores:
    """Stores over Postgres sessions."""

    @asynccontextmanager
    async def read() -> AsyncIterator[MediaRepos]:
        async with session_factory() as session:
            yield build_media_repos(session)

    @asynccontextmanager
    async def targets() -> AsyncIterator[AttachTargetAccess]:
        async with session_factory() as session:
            yield GraphAttachTargetAccess(build_graph_repos(session))

    return CoverStores(
        uow=lambda: create_media_uow(session_factory), read=read, targets=targets
    )


# ---- content: what the pack defines, read back from what was stored ----


# A cover's file is named "<item name> (<style>).png", which is how `inspect`
# recovers name and style: the media module stores nothing else about it.


def _cover_filename(name: str, style: str) -> str:
    return f"{name} ({style}).png"


def _cover_content(
    name: str | None, style: str | None, sha256: str | None
) -> dict[str, Any]:
    return {"style": style, "name": name, "sha256": sha256}


# ---- the targets ----


class CoverPackTarget:
    """Implements `CoverTarget` with the media use cases, run as `actor`.

    The cover's id is its attachment's id. Its content hash covers the stored
    asset's checksum only while the attachment is still the item's cover, so an
    image the person swapped in (or a demoted pack image) reads as an edit.
    """

    def __init__(
        self,
        stores: CoverStores,
        actor: Actor,
        *,
        renderer: CoverRenderer,
        storage: MediaStoragePort,
        policy: AttachmentPolicyPort,
        image_processor: ImageProcessorPort,
        access: AccessGuard | None = None,
    ) -> None:
        self._stores = stores
        self._actor = actor
        self._access = access or get_access_guard()
        self._scope = self._access.scope_for(actor)
        self._renderer = renderer
        self._storage = storage
        self._policy = policy
        self._image_processor = image_processor

    async def create(self, item_id: uuid.UUID, name: str, style: str) -> Created:
        """Draw the cover, attach it to the item and set it as the item's cover."""
        png = self._renderer.render(name, style)
        async with self._stores.targets() as targets:
            attachment = await UploadAndAttachMedia(
                self._stores.uow(),
                self._access,
                self._storage,
                self._policy,
                self._image_processor,
                targets,
            ).handle(
                UploadAndAttachMediaCommand(
                    filename=_cover_filename(name, style),
                    content_type="image/png",
                    sniffed_content_type="image/png",
                    stream=_single_chunk(png),
                    target_type=AttachmentTarget.NODE,
                    target_id=item_id,
                ),
                self._actor,
            )
        try:
            await SetMediaCover(self._stores.uow(), self._access).handle(
                SetMediaCoverCommand(
                    asset_id=attachment.asset_id,
                    target_type=AttachmentTarget.NODE,
                    target_id=item_id,
                ),
                self._actor,
            )
        except Exception:
            # Not yet recorded by the install, so it would be orphaned.
            await self.remove(attachment.id)
            raise
        return Created(
            entity_id=attachment.id,
            content=_cover_content(name, style, hashlib.sha256(png).hexdigest()),
        )

    async def has_cover(self, item_id: uuid.UUID) -> bool:
        """Whether any image is flagged as the item's cover."""
        async with self._stores.read() as repos:
            attached = await repos.attachments.list_for_target(
                AttachmentTarget.NODE, item_id, scope=self._scope
            )
        return any(a.attribute_key is AttachmentKey.COVER for a in attached)

    async def inspect(self, cover_id: uuid.UUID) -> Inspection | None:
        """Return the cover as it is now, or `None` if it is gone."""
        async with self._stores.read() as repos:
            attachment = await repos.attachments.get(cover_id, scope=self._scope)
            if attachment is None:
                return None
            asset = await repos.assets.get(attachment.asset_id, scope=self._scope)
        if asset is None:
            return None
        parsed = _COVER_FILENAME.fullmatch(asset.filename)
        is_cover = attachment.attribute_key is AttachmentKey.COVER
        return Inspection(
            content=_cover_content(
                parsed["name"] if parsed else None,
                parsed["style"] if parsed else None,
                asset.sha256 if is_cover else None,
            )
        )

    async def remove(self, cover_id: uuid.UUID) -> RemoveResult:
        """Purge the cover's attachment, and its asset and file if unused elsewhere."""
        async with self._stores.read() as repos:
            attachment = await repos.attachments.get(cover_id, scope=self._scope)
        if attachment is None:
            return RemoveResult.ALREADY_GONE
        await PurgeAttachment(self._stores.uow(), self._access, self._storage).handle(
            PurgeAttachmentCommand(attachment_id=attachment.id), SYSTEM_ACTOR
        )
        return RemoveResult.REMOVED


# ---- FastAPI providers ----


def get_cover_pack_target(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    policy: Annotated[AttachmentPolicyPort, Depends(get_attachment_policy)],
    image_processor: Annotated[ImageProcessorPort, Depends(get_image_processor)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> CoverPackTarget:
    """Return the cover target over Postgres, acting as the signed-in person."""
    return CoverPackTarget(
        build_cover_stores(session_factory),
        actor,
        renderer=PillowCoverRenderer(),
        storage=storage,
        policy=policy,
        image_processor=image_processor,
    )
