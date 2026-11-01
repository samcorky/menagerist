from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.modules.settings.application.settings_reader import CachedSettingsReader
from app.modules.settings.domain.errors import UnknownSettingError
from app.modules.settings.domain.setting import (
    Pin,
    SettingScope,
    SettingValue,
    StoredSetting,
)
from app.modules.settings.ports.unit_of_work import SettingsRepos
from app.shared_kernel.settings import SettingKey
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
        InMemorySettingValueRepository,
    )
    from app.modules.settings.adapters.platform.pydantic_settings_catalogue import (
        PydanticSettingsCatalogue,
    )

KEEP = SettingKey[int]("backup.keep_last")
SCHEDULE = SettingKey[str]("backup.schedule")
ZONE = SettingKey[str]("display.timezone")

type Stored = Callable[..., StoredSetting]
type Uow = Callable[[], InMemoryUnitOfWork[SettingsRepos]]


class Clock:
    """A settable monotonic clock."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current time."""
        return self.now


def reader(
    catalogue: PydanticSettingsCatalogue, uow: Uow, clock: Clock | None = None
) -> CachedSettingsReader:
    """A reader with a five-second cache."""
    return CachedSettingsReader(catalogue, uow, ttl=5, clock=clock or Clock())


async def test_nothing_set_returns_the_default(
    catalogue: PydanticSettingsCatalogue, uow: Uow
) -> None:
    """Without a pin or a row, the code default answers."""
    assert await reader(catalogue, uow).get(KEEP) == 7


async def test_a_saved_value_returns_instead_of_the_default(
    catalogue: PydanticSettingsCatalogue,
    uow: Uow,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """An administrator's value beats the default."""
    await repo.save(make_stored("backup.keep_last", 12))
    assert await reader(catalogue, uow).get(KEEP) == 12


async def test_a_stored_value_that_breaks_a_constraint_falls_back(
    catalogue: PydanticSettingsCatalogue,
    uow: Uow,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """Zero violates ge=1; the reader answers with the default instead of failing."""
    await repo.save(make_stored("backup.keep_last", 0))
    assert await reader(catalogue, uow).get(KEEP) == 7


async def test_a_deployment_pin_wins_over_a_saved_value(
    pinned_catalogue: PydanticSettingsCatalogue,
    uow: Uow,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """The environment value is returned even when a row says otherwise."""
    await repo.save(make_stored("backup.keep_last", 12))
    assert await reader(pinned_catalogue, uow).get(KEEP) == 30


async def test_a_pin_is_returned_without_opening_a_transaction(
    pinned_catalogue: PydanticSettingsCatalogue,
) -> None:
    """A pinned key never touches the database."""

    def never() -> InMemoryUnitOfWork[SettingsRepos]:
        msg = "must not open a transaction"
        raise AssertionError(msg)

    assert await CachedSettingsReader(pinned_catalogue, never).get(KEEP) == 30


async def test_rows_are_cached_until_the_ttl_passes(
    catalogue: PydanticSettingsCatalogue,
    uow: Uow,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """A change is seen after the TTL, not before."""
    clock = Clock()
    cached = reader(catalogue, uow, clock)
    assert await cached.get(KEEP) == 7
    await repo.save(make_stored("backup.keep_last", 12))
    clock.now = 4.9
    assert await cached.get(KEEP) == 7
    clock.now = 5.1
    assert await cached.get(KEEP) == 12


async def test_invalidate_shows_a_write_at_once(
    catalogue: PydanticSettingsCatalogue,
    uow: Uow,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """A writer drops the cache so its own process sees the change immediately."""
    cached = reader(catalogue, uow)
    assert await cached.get(SCHEDULE) == "0 3 * * *"
    await repo.save(make_stored("backup.schedule", ""))
    cached.invalidate()
    assert await cached.get(SCHEDULE) == ""


async def test_user_settings_are_read_per_owner(
    catalogue: PydanticSettingsCatalogue,
    uow: Uow,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """Two people have separate values; a third gets the default."""
    ann, bob, cy = uuid7(), uuid7(), uuid7()
    zone: SettingValue
    for owner, zone in ((ann, "Europe/London"), (bob, "Asia/Tokyo")):
        await repo.save(make_stored("display.timezone", zone, owner, SettingScope.USER))
    cached = reader(catalogue, uow)
    assert await cached.get(ZONE, user_id=ann) == "Europe/London"
    assert await cached.get(ZONE, user_id=bob) == "Asia/Tokyo"
    assert await cached.get(ZONE, user_id=cy) == "UTC"


async def test_a_user_key_needs_a_user(
    catalogue: PydanticSettingsCatalogue, uow: Uow
) -> None:
    """Reading a per-user key without saying whose is a programming error."""
    with pytest.raises(ValueError, match="user-scoped"):
        await reader(catalogue, uow).get(ZONE)


async def test_an_unknown_key_is_refused(
    catalogue: PydanticSettingsCatalogue, uow: Uow
) -> None:
    """A typo in a key fails loudly."""
    with pytest.raises(UnknownSettingError):
        await reader(catalogue, uow).get(SettingKey[int]("nope.nothing"))


def test_pin_is_a_plain_value() -> None:
    """A pin carries the variable name and the value."""
    assert Pin(env_name="X", value=1).value == 1
