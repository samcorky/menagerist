from typing import TYPE_CHECKING

from app.modules.media.domain.errors import UnsupportedMediaTypeError
from app.modules.media.domain.media_attachment import AttachmentTarget

if TYPE_CHECKING:
    from app.modules.media.domain.media_asset import MediaAsset

# None = unrestricted. A tuple of prefix strings = permitted prefixes.
_RULES: dict[AttachmentTarget, tuple[str, ...] | None] = {
    AttachmentTarget.NODE: None,
    AttachmentTarget.EDGE: None,
}


class ContentTypeAttachmentPolicy:
    """Table-driven content-type gate.

    Each target maps to either ``None`` (unrestricted) or a tuple of permitted
    ``content_type`` prefixes (e.g. ``("image/",)`` for images only).
    """

    async def check(self, target: AttachmentTarget, asset: MediaAsset) -> None:
        """Raise ``UnsupportedMediaTypeError`` if the content type is not permitted."""
        permitted = _RULES.get(target)
        if permitted is None:
            return
        if not any(asset.content_type.startswith(p) for p in permitted):
            raise UnsupportedMediaTypeError(
                f"{asset.content_type!r} not permitted for {target.value} attachments"
            )
