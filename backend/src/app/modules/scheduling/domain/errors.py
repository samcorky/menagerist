"""Scheduling errors translated by the shared exception handlers."""

from app.shared_kernel.errors import ConflictError, NotFoundError


class InvalidRunTransitionError(ConflictError):
    """A run cannot enter the requested state."""


class LostClaimError(ConflictError):
    """The caller no longer owns a running job."""


class UnknownRunError(NotFoundError):
    """No run exists with the requested identifier."""


class UnknownJobError(NotFoundError):
    """No job is registered with the requested key."""


class DuplicateJobError(ConflictError):
    """A job key was registered more than once."""
