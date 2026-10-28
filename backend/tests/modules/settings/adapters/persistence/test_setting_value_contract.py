"""Repository contracts shared by the in-memory and Postgres adapters."""

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.persistence.unit_of_work import build_settings_repos
from app.modules.settings.domain.setting import (
    SettingScope,
    SettingValue,
    StoredSetting,
)

if TYPE_CHECKING:
    from app.modules.settings.ports.setting_value_repository import (
        SettingValueRepository,
    )

type Stored = Callable[..., StoredSetting]


@pytest.fixture(
    params=["memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def values(request: pytest.FixtureRequest) -> SettingValueRepository:
    """Exercise the same contract against both implementations."""
    if request.param == "memory":
        return InMemorySettingValueRepository()
    return build_settings_repos(request.getfixturevalue("db_session")).values


@pytest.mark.parametrize(
    "value", [True, 0, 12, 1.5, "", "0 3 * * *", [], ["a", "b"]], ids=repr
)
async def test_every_flat_value_round_trips(
    values: SettingValueRepository, make_stored: Stored, value: SettingValue
) -> None:
    """Booleans, numbers, strings and lists of strings come back as saved."""
    key = f"contract.{uuid7().hex}"
    await values.save(make_stored(key, value))
    got = await values.get(SettingScope.INSTANCE, None, key)
    assert got is not None
    assert got.value == value
    assert type(got.value) is type(value)


async def test_saving_again_replaces_the_value_and_audit_fields(
    values: SettingValueRepository, make_stored: Stored
) -> None:
    """An address holds one row; a second save overwrites it."""
    key = f"contract.{uuid7().hex}"
    editor = uuid7()
    first = make_stored(key, 7)
    await values.save(first)
    second = make_stored(key, 12)
    second.updated_by = editor
    await values.save(second)
    rows = await values.list(SettingScope.INSTANCE, None)
    assert rows[key].value == 12
    assert rows[key].updated_by == editor
    assert rows[key].updated_at == second.updated_at


async def test_user_rows_are_isolated_by_owner_and_scope(
    values: SettingValueRepository, make_stored: Stored
) -> None:
    """Two people and the instance can hold the same key without clashing."""
    key = f"contract.{uuid7().hex}"
    ann, bob = uuid7(), uuid7()
    await values.save(make_stored(key, "UTC", ann, SettingScope.USER))
    await values.save(make_stored(key, "Asia/Tokyo", bob, SettingScope.USER))
    await values.save(make_stored(key, "instance"))
    await values.save(make_stored(key, "Europe/London", ann, SettingScope.USER))

    ann_row = await values.get(SettingScope.USER, ann, key)
    bob_row = await values.get(SettingScope.USER, bob, key)
    instance_row = await values.get(SettingScope.INSTANCE, None, key)
    assert ann_row is not None and ann_row.value == "Europe/London"  # noqa: PT018
    assert bob_row is not None and bob_row.value == "Asia/Tokyo"  # noqa: PT018
    assert instance_row is not None and instance_row.value == "instance"  # noqa: PT018
    assert set(await values.list(SettingScope.USER, ann)) == {key}
    assert await values.get(SettingScope.USER, uuid7(), key) is None


async def test_delete_reports_whether_a_value_existed(
    values: SettingValueRepository, make_stored: Stored
) -> None:
    """Resetting twice is harmless and tells the caller what happened."""
    key = f"contract.{uuid7().hex}"
    await values.save(make_stored(key, 12))
    assert await values.delete(SettingScope.INSTANCE, None, key) is True
    assert await values.delete(SettingScope.INSTANCE, None, key) is False
    assert await values.get(SettingScope.INSTANCE, None, key) is None


async def test_delete_only_touches_its_own_address(
    values: SettingValueRepository, make_stored: Stored
) -> None:
    """Removing one person's value leaves another's and the instance's."""
    key = f"contract.{uuid7().hex}"
    ann, bob = uuid7(), uuid7()
    await values.save(make_stored(key, "a", ann, SettingScope.USER))
    await values.save(make_stored(key, "b", bob, SettingScope.USER))
    await values.save(make_stored(key, "c"))
    await values.delete(SettingScope.USER, ann, key)
    assert await values.get(SettingScope.USER, bob, key) is not None
    assert await values.get(SettingScope.INSTANCE, None, key) is not None
