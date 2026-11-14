"""Errors raised for malformed bundle content and impossible run changes."""

from app.shared_kernel.errors import ConflictError, ValidationError


class InvalidBundleError(ValidationError):
    """Raised when a bundle file or its content is malformed."""


class InvalidRunStateError(ConflictError):
    """Raised when a run is asked to make an impossible change."""
