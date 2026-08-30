from app.shared_kernel.errors import ConflictError, NotFoundError


class NodeNotFoundError(NotFoundError):
    """Raised when a requested node does not exist."""


class EdgeNotFoundError(NotFoundError):
    """Raised when a requested edge does not exist."""


class NodeTypeNotFoundError(NotFoundError):
    """Raised when a requested node type does not exist."""


class NodeTypeSlugConflictError(ConflictError):
    """Raised when a node type with the given slug already exists."""
