"""What settings exist and what the deployment pins."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.settings.domain.setting import (
        Pin,
        SettingDescriptor,
        SettingScope,
        SettingValue,
    )


class SettingsCatalogue(Protocol):
    """The tunable settings, their deployment pins and their validation."""

    def descriptors(self, scope: SettingScope) -> list[SettingDescriptor]:
        """List the settings of one scope in a stable order."""
        ...

    def descriptor(self, key: str) -> SettingDescriptor:
        """Return one setting; raises `UnknownSettingError`."""
        ...

    def pin(self, key: str) -> Pin | None:
        """Return the value the deployment supplies, if any."""
        ...

    def normalise(self, key: str, value: object) -> SettingValue:
        """Validate a value with the setting's own constraints.

        Raises:
            InvalidSettingValueError: If the value is not acceptable.
        """
        ...

    def to_python(self, key: str, value: SettingValue) -> object:
        """Turn a stored value into the type the setting reads as."""
        ...
