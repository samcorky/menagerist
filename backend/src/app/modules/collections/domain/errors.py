from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class InvalidCollectionError(ValidationError):
    """Raised when a collection's name or other field is not acceptable."""


class CollectionNotFoundError(NotFoundError):
    """Raised when a requested collection does not exist."""


class CollectionKindError(ConflictError):
    """Raised when an operation does not suit the collection's kind."""


class InvalidDefinitionError(InvalidCollectionError):
    """Raised when a smart collection's definition cannot be used.

    `path` locates the first bad condition in the definition, or is empty.
    """

    def __init__(self, message: str, *, path: str = "") -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path
