from typing import Self

from app.shared_kernel.permission import PermissionEnum


class BackupPermission(PermissionEnum):
    """Instance archives (administrators) and a member's own data export/import."""

    CREATE = "backup:archive:create"
    READ = "backup:archive:read"
    RESTORE = "backup:archive:restore"
    DELETE = "backup:archive:delete"
    EXPORT_OWN_DATA = "backup:own_data:export"
    IMPORT_OWN_DATA = "backup:own_data:import"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants."""
        cls = type(self)
        if self in (cls.CREATE, cls.RESTORE):
            return frozenset({cls.READ})
        return frozenset()
