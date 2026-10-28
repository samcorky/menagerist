"""A `SettingsCatalogue` over explicit descriptors, validated with Pydantic.

It holds no infrastructure, so tests build it directly and it plays the in-memory
sibling's part; the composition root builds the real one from discovered settings.
"""

from typing import TYPE_CHECKING, cast

from pydantic import TypeAdapter, ValidationError

from app.modules.settings.domain.errors import (
    InvalidSettingValueError,
    UnknownSettingError,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from app.modules.settings.domain.setting import (
        Pin,
        SettingDescriptor,
        SettingScope,
        SettingValue,
    )


class PydanticSettingsCatalogue:
    """Validate each setting with a Pydantic adapter, optionally pinned by `pins`."""

    def __init__(
        self,
        descriptors: Iterable[SettingDescriptor],
        adapters: Mapping[str, TypeAdapter[object]],
        pins: Mapping[str, Pin] | None = None,
    ) -> None:
        self._descriptors = {d.key: d for d in descriptors}
        self.adapters = dict(adapters)
        self._pins = dict(pins or {})

    def descriptors(self, scope: SettingScope) -> list[SettingDescriptor]:
        """List the settings of one scope."""
        return [d for d in self._descriptors.values() if d.scope is scope]

    def descriptor(self, key: str) -> SettingDescriptor:
        """Return one setting or raise `UnknownSettingError`."""
        try:
            return self._descriptors[key]
        except KeyError:
            raise UnknownSettingError(key) from None

    def pin(self, key: str) -> Pin | None:
        """Return the pinned value for a key, if any."""
        self.descriptor(key)
        return self._pins.get(key)

    def normalise(self, key: str, value: object) -> SettingValue:
        """Validate with the setting's adapter and return its JSON form."""
        adapter = self.adapters[self.descriptor(key).key]
        try:
            python = adapter.validate_python(value)
        except ValidationError as exc:
            reason = "; ".join(error["msg"] for error in exc.errors())
            raise InvalidSettingValueError(key, reason) from exc
        return cast("SettingValue", adapter.dump_python(python, mode="json"))

    def to_python(self, key: str, value: SettingValue) -> object:
        """Validate a stored value into the type the setting reads as."""
        return self.adapters[self.descriptor(key).key].validate_python(value)
