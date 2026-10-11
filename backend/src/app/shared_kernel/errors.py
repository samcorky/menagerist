from typing import ClassVar


class DomainError(Exception):
    """Base type for exceptions raised by domain/application code."""

    # RFC 9457 `type` of the problem response; subclasses may name their own.
    problem_type: ClassVar[str] = "about:blank"


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""


class ConflictError(DomainError):
    """Raised when an operation conflicts with existing state."""


class ValidationError(DomainError):
    """Raised when input fails a domain invariant."""


class ForbiddenError(DomainError):
    """Raised when an actor is not permitted to perform an action."""


class UnauthenticatedError(DomainError):
    """Raised when the caller has not proved who they are."""


class TooManyRequestsError(DomainError):
    """Raised when the caller must wait before trying again."""

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
