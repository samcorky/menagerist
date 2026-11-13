"""Errors raised for malformed bundle content."""

from app.shared_kernel.errors import ValidationError


class InvalidPackError(ValidationError):
    """Raised when a pack file or its content is malformed."""
