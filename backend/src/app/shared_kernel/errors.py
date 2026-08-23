class DomainError(Exception):
    """Base type for exceptions raised by domain/application code."""


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""


class ConflictError(DomainError):
    """Raised when an operation conflicts with existing state."""


class ValidationError(DomainError):
    """Raised when input fails a domain invariant."""


class ForbiddenError(DomainError):
    """Raised when an actor is not permitted to perform an action."""
