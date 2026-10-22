from typing import Self

from app.shared_kernel.permission import PermissionEnum


class IdentityPermission(PermissionEnum):
    """Permissions for managing other people's accounts.

    Values read `<module>:<resource>:<action>`.
    """

    CREATE_USER = "identity:user:create"
    LIST_USERS = "identity:user:list"
    UPDATE_USER = "identity:user:update"
    RESET_USER_PASSWORD = "identity:user:reset_password"
    UNLOCK_USER = "identity:user:unlock"
    LIST_SESSIONS = "identity:session:list"
    REVOKE_SESSION = "identity:session:revoke"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants.

        Managing accounts needs seeing them; revoking a session needs listing it.
        """
        cls = type(self)
        match self:
            case (
                cls.CREATE_USER
                | cls.UPDATE_USER
                | cls.RESET_USER_PASSWORD
                | cls.UNLOCK_USER
            ):
                return frozenset({cls.LIST_USERS})
            case cls.REVOKE_SESSION:
                return frozenset({cls.LIST_SESSIONS})
            case _:
                return frozenset()
