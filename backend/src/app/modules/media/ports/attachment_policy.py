from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.media.domain.media_asset import MediaAsset
    from app.modules.media.domain.media_attachment import AttachmentTarget


class AttachmentPolicyPort(Protocol):
    """Gate that enforces content-type rules per attachment target.

    Implementations raise `UnsupportedMediaTypeError` when the asset's
    content-type is not permitted for the given target.
    """

    async def check(
        self,
        target: AttachmentTarget,
        asset: MediaAsset,
    ) -> None:
        """Raise ``UnsupportedMediaTypeError`` if the content type is not permitted."""
        ...
