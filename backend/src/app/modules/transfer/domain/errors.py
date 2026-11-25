"""Errors raised for malformed bundle content and impossible run changes."""

from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


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


class ImportNotFoundError(NotFoundError):
    """Raised when the person has no uploaded import file with the id."""


class InvalidImportStateError(ConflictError):
    """Raised when an uploaded import is asked to do something its status forbids."""


class ImportFileTooLargeError(ValidationError):
    """Raised when an uploaded import file is over the size limit."""
