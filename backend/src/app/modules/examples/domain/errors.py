from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class PackNotFoundError(NotFoundError):
    """Raised when an example pack id is not in the catalogue."""


class PackAlreadyInstalledError(ConflictError):
    """Raised when installing a pack that is installed or only half installed."""


class PackNotInstalledError(ConflictError):
    """Raised when removing a pack that is not installed."""


class SlugClashError(ConflictError):
    """Raised when a type the pack would create already exists."""

    def __init__(self, *, kind: str, slug: str) -> None:
        """Build the message from the kind of type and the clashing slug."""
        advice = "Rename or remove it, then try again."
        super().__init__(f"You already have {kind} called '{slug}'. {advice}")
        self.kind = kind
        self.slug = slug


class InvalidPackError(ValidationError):
    """Raised when a pack file or its content is malformed."""


class InvalidInstallationStateError(ConflictError):
    """Raised when an installation is asked to make an impossible change."""


class InstallFailedError(Exception):
    """Raised when an install failed part-way and was rolled back.

    Deliberately not a `DomainError`: it is a server-side failure, so the API
    reports it through the catch-all handler as a 500 problem response.
    """
