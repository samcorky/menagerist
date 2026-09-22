from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class PresetNotFoundError(NotFoundError):
    """Raised when a preset id does not resolve to a live preset."""


class InvalidPresetDefinitionError(ValidationError):
    """Raised when a preset's `kind` or `definition` is malformed."""


class BuiltinPresetError(ConflictError):
    """Raised when trying to update or delete a built-in preset."""
