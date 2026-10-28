"""Administrative access to instance settings."""

from typing import Self

from app.shared_kernel.permission import PermissionEnum


class SettingsPermission(PermissionEnum):
    """Instance settings are administrator-only and not content-scoped."""

    READ = "settings:instance:read"
    WRITE = "settings:instance:write"

    def implied(self) -> frozenset[Self]:
        """Changing a setting also permits reading it."""
        cls = type(self)
        return frozenset({cls.READ}) if self is cls.WRITE else frozenset()
