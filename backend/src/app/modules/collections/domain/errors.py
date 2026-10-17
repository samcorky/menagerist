from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class InvalidCollectionError(ValidationError):
    """Raised when a collection's name or other field is not acceptable."""


class CollectionNotFoundError(NotFoundError):
    """Raised when a requested collection does not exist."""


class CollectionKindError(ConflictError):
    """Raised when an operation does not suit the collection's kind."""
