from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class SystemPermission(StrEnum):
    """Permissions for operational detail the public probes leave out.

    Values read `<module>:<resource>:<action>`.
    """

    READ_DIAGNOSTICS = "system:diagnostics:read"


# Holding the key also grants the values. None yet.
IMPLIES: Mapping[SystemPermission, frozenset[SystemPermission]] = {}
