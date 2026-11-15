from typing import Self

from app.shared_kernel.permission import PermissionEnum


class TransferPermission(PermissionEnum):
    """Permissions for importing and exporting bundle files.

    Exporting a file is `BUNDLE_READ`, so a read-only token can export. The
    targets underneath still check the permission for each kind of thing a bundle
    holds, such as saving presets.
    """

    BUNDLE_READ = "transfer:bundle:read"
    BUNDLE_IMPORT = "transfer:bundle:import"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants: nothing."""
        return frozenset()
