"""Errors raised for malformed bundle content and impossible run changes."""

from app.shared_kernel.errors import ConflictError, ValidationError


class InvalidBundleError(ValidationError):
    """Raised when a bundle file or its content is malformed."""


class InvalidRunStateError(ConflictError):
    """Raised when a run is asked to make an impossible change."""


class BundleConflictError(ConflictError):
    """Raised when a bundle is applied although its plan has conflicts."""


class InvalidImportFileError(ValidationError):
    """Raised when a spreadsheet file or the mapping given for it cannot be imported."""


class CellValueError(ValidationError):
    """Raised when a spreadsheet cell cannot become its field's value."""


class UnknownFormatError(ValidationError):
    """Raised when no codec reads or writes the named format."""
