from app.modules.media.application.attach_media import AttachMedia
from app.modules.media.application.claim_orphaned_media import ClaimOrphanedMedia
from app.modules.media.application.cleanup_expired_media import CleanupExpiredMedia
from app.modules.media.application.clear_media_cover import ClearMediaCover
from app.modules.media.application.delete_media import DeleteMedia
from app.modules.media.application.detach_media import DetachMedia
from app.modules.media.application.get_media import GetMedia
from app.modules.media.application.list_node_media import ListNodeMedia
from app.modules.media.application.orphan_media import OrphanMedia
from app.modules.media.application.promote_media import PromoteMedia
from app.modules.media.application.regenerate_thumbnails import RegenerateThumbnails
from app.modules.media.application.set_media_cover import SetMediaCover
from app.modules.media.application.stage_media import StageMedia
from app.modules.media.application.update_media import UpdateMedia
from app.modules.media.application.upload_and_attach_media import UploadAndAttachMedia
from app.shared_kernel.access import Content, System


def test_content_use_cases_are_owner_scoped() -> None:
    """Each person sees and changes only their own content."""
    for use_case in (
        AttachMedia,
        CleanupExpiredMedia,
        ClearMediaCover,
        DeleteMedia,
        DetachMedia,
        GetMedia,
        ListNodeMedia,
        OrphanMedia,
        PromoteMedia,
        RegenerateThumbnails,
        SetMediaCover,
        StageMedia,
        UpdateMedia,
        UploadAndAttachMedia,
    ):
        assert use_case.access == Content()


def test_claim_jobs_are_system_only() -> None:
    """Only the system actor hands pre-account content to the first owner."""
    for use_case in (ClaimOrphanedMedia,):
        assert use_case.access == System()
