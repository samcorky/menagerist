from typing import ClassVar


class MenageristError(Exception):
    """Root of every exception Menagerist raises on purpose.

    Anything that is not a `MenageristError` is a bug or a library failure.
    """


class InfrastructureError(MenageristError):
    """A failure outside the domain rules: a service, file or network gave way.

    Not the caller's mistake, so the API answers 500 and the message is logged,
    never sent: it may carry paths or addresses.
    """


class DomainError(MenageristError):
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
