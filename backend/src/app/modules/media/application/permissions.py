from typing import Self

from app.shared_kernel.permission import PermissionEnum


class MediaPermission(PermissionEnum):
    """Permissions for media on a user's own items."""

    ITEM_READ = "media:item:read"
    ITEM_WRITE = "media:item:write"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants."""
        cls = type(self)
        if self is cls.ITEM_WRITE:
            return frozenset({cls.ITEM_READ})
        return frozenset()
