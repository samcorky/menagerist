from app.shared_kernel.errors import NotFoundError, ValidationError


class MediaAssetNotFoundError(NotFoundError):
    """Raised when a requested media asset does not exist."""


class MediaFileTooLargeError(ValidationError):
    """Raised when an upload exceeds the configured maximum file size."""
