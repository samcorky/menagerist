from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class PresetNotFoundError(NotFoundError):
    """Raised when a preset id does not resolve to a live preset."""


class InvalidPresetDefinitionError(ValidationError):
    """Raised when a preset's `kind` or `definition` is malformed."""


class PresetInUseError(ConflictError):
    """Raised when deleting a preset that item types still reference."""
