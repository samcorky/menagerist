from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class IdentityPermission(StrEnum):
    """Permissions for managing other people's accounts.

    Values read `<module>:<resource>:<action>`.
    """

    CREATE_USER = "identity:user:create"
    LIST_USERS = "identity:user:list"
    UPDATE_USER = "identity:user:update"
    RESET_USER_PASSWORD = "identity:user:reset_password"
    UNLOCK_USER = "identity:user:unlock"


# Holding the key also grants the values: managing accounts needs seeing them.
IMPLIES: Mapping[IdentityPermission, frozenset[IdentityPermission]] = {
    IdentityPermission.CREATE_USER: frozenset({IdentityPermission.LIST_USERS}),
    IdentityPermission.UPDATE_USER: frozenset({IdentityPermission.LIST_USERS}),
    IdentityPermission.RESET_USER_PASSWORD: frozenset({IdentityPermission.LIST_USERS}),
    IdentityPermission.UNLOCK_USER: frozenset({IdentityPermission.LIST_USERS}),
}
