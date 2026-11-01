from typing import Self

from app.shared_kernel.permission import PermissionEnum


class PresetPermission(PermissionEnum):
    """Permissions for field presets."""

    PRESET_READ = "presets:preset:read"
    PRESET_WRITE = "presets:preset:write"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants."""
        cls = type(self)
        if self is cls.PRESET_WRITE:
            return frozenset({cls.PRESET_READ})
        return frozenset()
