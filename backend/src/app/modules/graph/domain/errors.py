from app.shared_kernel.errors import NotFoundError


class NodeNotFoundError(NotFoundError):
    """Raised when a requested node does not exist."""
