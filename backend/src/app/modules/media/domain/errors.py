from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class MediaAssetNotFoundError(NotFoundError):
    """Raised when a requested media asset does not exist."""


class MediaFileTooLargeError(ValidationError):
    """Raised when an upload exceeds the configured maximum file size."""


class MediaAttachmentNotFoundError(NotFoundError):
    """Raised when a requested media attachment record does not exist."""


class UnsupportedMediaTypeError(ValidationError):
    """Raised when a file's content-type is not permitted for the attachment target."""


class ThumbnailNotAvailableError(NotFoundError):
    """Raised when a thumbnail is requested for an asset that has none."""


COVER_ALREADY_SET_MESSAGE = "This item already has a cover. Set another image as the cover instead, or clear the cover first."  # noqa: E501


class CoverAlreadySetError(ConflictError):
    """Raised when a cover is attached to an item that already has one."""

    def __init__(self) -> None:
        super().__init__(COVER_ALREADY_SET_MESSAGE)
