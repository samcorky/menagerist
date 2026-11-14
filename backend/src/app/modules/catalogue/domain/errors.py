from app.shared_kernel.errors import NotFoundError, ValidationError


class CatalogueEntryNotFoundError(NotFoundError):
    """Raised when a catalogue entry id is not one the app ships."""


class InvalidEntryError(ValidationError):
    """Raised when a catalogue entry, or the file it is read from, is malformed."""
