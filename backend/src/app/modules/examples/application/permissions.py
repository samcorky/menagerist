from typing import Self

from app.shared_kernel.permission import PermissionEnum


class ExamplePermission(PermissionEnum):
    """Permissions for example packs."""

    PACK_READ = "examples:pack:read"
    PACK_INSTALL = "examples:pack:install"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants."""
        cls = type(self)
        if self is cls.PACK_INSTALL:
            return frozenset({cls.PACK_READ})
        return frozenset()
