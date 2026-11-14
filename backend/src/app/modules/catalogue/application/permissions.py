from typing import Self

from app.shared_kernel.permission import PermissionEnum


class CataloguePermission(PermissionEnum):
    """Permissions for the catalogue of installable presets and starter types."""

    ENTRY_READ = "catalogue:entry:read"
    ENTRY_INSTALL = "catalogue:entry:install"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants."""
        cls = type(self)
        if self is cls.ENTRY_INSTALL:
            return frozenset({cls.ENTRY_READ})
        return frozenset()
