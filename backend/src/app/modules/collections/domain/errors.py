from app.shared_kernel.errors import NotFoundError, ValidationError


class InvalidCollectionError(ValidationError):
    """Raised when a collection's name or other field is not acceptable."""


class CollectionNotFoundError(NotFoundError):
    """Raised when a requested collection does not exist."""
