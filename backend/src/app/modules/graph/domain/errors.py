from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class InvalidSchemaError(ValidationError):
    """Raised when attributes_schema is not valid JSON Schema."""


class InvalidAttributesError(ValidationError):
    """Raised when node or edge attributes fail schema validation."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.validation_errors = errors
        super().__init__(errors[0]["message"] if errors else "Invalid attributes")


class NodeNotFoundError(NotFoundError):
    """Raised when a requested node does not exist."""


class EdgeNotFoundError(NotFoundError):
    """Raised when a requested edge does not exist."""


class NodeTypeNotFoundError(NotFoundError):
    """Raised when a requested node type does not exist."""


class NodeTypeSlugConflictError(ConflictError):
    """Raised when a node type with the given slug already exists."""


class EdgeTypeNotFoundError(NotFoundError):
    """Raised when a requested edge type does not exist."""


class EdgeTypeSlugConflictError(ConflictError):
    """Raised when an edge type with the given slug already exists."""


class EdgeTypeInUseError(ConflictError):
    """Raised when deleting an edge type still referenced by existing edges."""
