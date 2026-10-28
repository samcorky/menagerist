"""What a setting is, where its value came from, and how the layers combine."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

if TYPE_CHECKING:
    from collections.abc import Callable

# Tunables are flat: one JSON scalar or a list of strings.
type SettingValue = bool | int | float | str | list[str]


class SettingScope(StrEnum):
    """Who owns the stored value."""

    INSTANCE = "instance"
    USER = "user"


class SettingSource(StrEnum):
    """Which layer supplied the effective value."""

    DEFAULT = "default"
    INSTANCE = "instance"
    USER = "user"
    ENV = "env"


@dataclass(frozen=True, kw_only=True)
class SettingDescriptor:
    """The static description of one tunable setting."""

    key: str
    group: str
    title: str
    description: str | None
    scope: SettingScope
    restart_required: bool
    default: SettingValue
    # JSON Schema of the value, with `x-menagerist` hints; rendered by the form.
    schema: dict[str, object] = field(default_factory=dict)
    env_name: str | None = None


@dataclass(frozen=True, kw_only=True)
class Pin:
    """A value the deployment supplies through the environment, which wins over all."""

    env_name: str
    value: SettingValue


@dataclass(kw_only=True, eq=False)
class StoredSetting:
    """A value saved by an administrator or a person."""

    id: UUID
    scope: SettingScope
    owner_id: UUID | None
    key: str
    value: SettingValue
    updated_at: datetime
    updated_by: UUID | None

    @classmethod
    def create(
        cls,
        *,
        scope: SettingScope,
        owner_id: UUID | None,
        key: str,
        value: SettingValue,
        updated_by: UUID | None,
    ) -> StoredSetting:
        """Build a new row; instance rows have no owner, user rows must have one."""
        if (scope is SettingScope.USER) != (owner_id is not None):
            msg = "A user-scoped setting needs an owner and an instance one has none"
            raise ValueError(msg)
        return cls(
            id=uuid7(),
            scope=scope,
            owner_id=owner_id,
            key=key,
            value=value,
            updated_at=datetime.now(UTC),
            updated_by=updated_by,
        )

    def change(self, value: SettingValue, updated_by: UUID | None) -> None:
        """Replace the value and record who and when."""
        self.value = value
        self.updated_by = updated_by
        self.updated_at = datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class ResolvedSetting:
    """A descriptor with its effective value and where that value came from."""

    descriptor: SettingDescriptor
    value: SettingValue
    source: SettingSource
    locked: bool
    env_name: str | None
    # A stored value that no longer validates is ignored and flagged.
    stored_invalid: bool = False


def resolve(
    descriptor: SettingDescriptor,
    *,
    pin: Pin | None,
    stored: SettingValue | None,
    is_valid: Callable[[SettingValue], bool],
) -> ResolvedSetting:
    """Combine the layers: deployment pin, then the stored value, then the default."""
    if pin is not None:
        return ResolvedSetting(
            descriptor=descriptor,
            value=pin.value,
            source=SettingSource.ENV,
            locked=True,
            env_name=pin.env_name,
        )
    stored_source = (
        SettingSource.USER
        if descriptor.scope is SettingScope.USER
        else SettingSource.INSTANCE
    )
    if stored is not None and is_valid(stored):
        return ResolvedSetting(
            descriptor=descriptor,
            value=stored,
            source=stored_source,
            locked=False,
            env_name=descriptor.env_name,
        )
    return ResolvedSetting(
        descriptor=descriptor,
        value=descriptor.default,
        source=SettingSource.DEFAULT,
        locked=False,
        env_name=descriptor.env_name,
        stored_invalid=stored is not None,
    )
