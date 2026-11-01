from enum import StrEnum
from typing import Self


class PermissionEnum(StrEnum):
    """Base for a module's permissions; members declare what they imply."""

    def implied(self) -> frozenset[Self]:
        """Return the permissions this one grants directly."""
        return frozenset()
