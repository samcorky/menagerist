from app.shared_kernel.permission import PermissionEnum


class SystemPermission(PermissionEnum):
    """Permissions for operational detail the public probes leave out.

    Values read `<module>:<resource>:<action>`.
    """

    READ_DIAGNOSTICS = "system:diagnostics:read"
