from app.shared_kernel.errors import NotFoundError, ValidationError


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
