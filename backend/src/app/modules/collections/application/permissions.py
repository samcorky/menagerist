from typing import Self

from app.shared_kernel.permission import PermissionEnum


class CollectionPermission(PermissionEnum):
    """Permissions for a user's collections."""

    COLLECTION_READ = "collections:collection:read"
    COLLECTION_WRITE = "collections:collection:write"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants."""
        cls = type(self)
        if self is cls.COLLECTION_WRITE:
            return frozenset({cls.COLLECTION_READ})
        return frozenset()
