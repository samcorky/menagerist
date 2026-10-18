from app.shared_kernel.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class BackupNotFoundError(NotFoundError):
    """The requested backup does not exist."""


class CorruptBackupError(ValidationError):
    """The archive failed integrity or structural validation."""


class IncompatibleBackupError(ConflictError):
    """The archive's revision, format or scope cannot be restored here."""


class RestoreTargetNotEmptyError(ConflictError):
    """Restore would overwrite existing instance content."""


class BackupStorageError(DomainError):
    """The backup directory is missing or unwritable.

    Bind-mounted host directories must be writable by container uid 1000:
    run `chown 1000:1000 <host directory>`.
    """


class MediaFileMissingError(NotFoundError):
    """A referenced original media file is absent from storage."""
