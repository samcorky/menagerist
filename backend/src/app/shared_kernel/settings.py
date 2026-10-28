"""Typed setting keys and the port other modules read settings through."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True)
class SettingKey[T]:
    """The name of a tunable setting and, through `T`, the type it reads as."""

    key: str


class SettingsReader(Protocol):
    """Resolve a setting to its effective value: deployment pin, stored row, default."""

    async def get[T](self, key: SettingKey[T], *, user_id: UUID | None = None) -> T:
        """Return the effective value; `user_id` owns a user-scoped key."""
        ...
