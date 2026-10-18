from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class BackupPermission(StrEnum):
    """Administrator permissions for instance archives."""

    CREATE = "backup:archive:create"
    READ = "backup:archive:read"
    RESTORE = "backup:archive:restore"
    DELETE = "backup:archive:delete"


IMPLIES: Mapping[BackupPermission, frozenset[BackupPermission]] = {
    BackupPermission.CREATE: frozenset({BackupPermission.READ}),
    BackupPermission.RESTORE: frozenset({BackupPermission.READ}),
}
