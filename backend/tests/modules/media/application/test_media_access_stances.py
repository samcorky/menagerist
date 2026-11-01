from typing import TYPE_CHECKING, Any

from app.modules.media.application.attach_media import AttachMedia
from app.modules.media.application.claim_orphaned_media import ClaimOrphanedMedia
from app.modules.media.application.cleanup_expired_media import CleanupExpiredMedia
from app.modules.media.application.clear_media_cover import ClearMediaCover
from app.modules.media.application.delete_media import DeleteMedia
from app.modules.media.application.detach_media import DetachMedia
from app.modules.media.application.get_media import GetMedia
from app.modules.media.application.list_node_media import ListNodeMedia
from app.modules.media.application.orphan_media import OrphanMedia
from app.modules.media.application.permissions import MediaPermission
from app.modules.media.application.promote_media import PromoteMedia
from app.modules.media.application.regenerate_thumbnails import RegenerateThumbnails
from app.modules.media.application.set_media_cover import SetMediaCover
from app.modules.media.application.stage_media import StageMedia
from app.modules.media.application.update_media import UpdateMedia
from app.modules.media.application.upload_and_attach_media import UploadAndAttachMedia
from app.shared_kernel.access import Access, Content, System

if TYPE_CHECKING:
    from app.shared_kernel.cqrs import UseCase


READ = Content(MediaPermission.ITEM_READ)
WRITE = Content(MediaPermission.ITEM_WRITE)

STANCES: dict[type[UseCase[Any, Any]], Access] = {
    GetMedia: READ,
    ListNodeMedia: READ,
    AttachMedia: WRITE,
    ClearMediaCover: WRITE,
    DeleteMedia: WRITE,
    DetachMedia: WRITE,
    OrphanMedia: WRITE,
    PromoteMedia: WRITE,
    SetMediaCover: WRITE,
    StageMedia: WRITE,
    UpdateMedia: WRITE,
    UploadAndAttachMedia: WRITE,
}


def test_media_use_cases_need_the_item_permissions() -> None:
    """Each person sees and changes only their own media, given the permission."""
    assert {use_case: use_case.access for use_case in STANCES} == STANCES


def test_upload_and_attach_needs_what_its_inner_use_cases_need() -> None:
    """The composite runs StageMedia and AttachMedia under the same actor."""
    needed = {UploadAndAttachMedia.access, StageMedia.access, AttachMedia.access}
    assert needed == {Content(MediaPermission.ITEM_WRITE)}


def test_system_jobs_are_system_only() -> None:
    """Claiming and the clean-up and rebuild jobs are for the system actor only."""
    for use_case in (ClaimOrphanedMedia, CleanupExpiredMedia, RegenerateThumbnails):
        assert use_case.access == System()
