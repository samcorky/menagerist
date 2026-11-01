from typing import TYPE_CHECKING, Annotated
from uuid import uuid7

import pytest
from pydantic import Field, TypeAdapter

from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.platform.pydantic_settings_catalogue import (
    PydanticSettingsCatalogue,
)
from app.modules.settings.domain.errors import (
    InvalidSettingValueError,
    UnknownSettingError,
)
from app.modules.settings.domain.setting import (
    Pin,
    SettingDescriptor,
    SettingScope,
    StoredSetting,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_catalogue_lists_by_scope_and_looks_up_by_key(
    catalogue: PydanticSettingsCatalogue,
) -> None:
    """Descriptors are filtered by scope."""
    assert [d.key for d in catalogue.descriptors(SettingScope.INSTANCE)] == [
        "backup.keep_last",
        "backup.schedule",
    ]
    assert catalogue.descriptor("display.timezone").scope is SettingScope.USER
    with pytest.raises(UnknownSettingError):
        catalogue.descriptor("nope")


def test_catalogue_validates_with_the_field_constraints(
    catalogue: PydanticSettingsCatalogue,
) -> None:
    """The adapter keeps ge=1, which the bare annotation would drop."""
    assert catalogue.normalise("backup.keep_last", 12) == 12
    with pytest.raises(InvalidSettingValueError, match=r"backup\.keep_last"):
        catalogue.normalise("backup.keep_last", 0)
    with pytest.raises(InvalidSettingValueError):
        catalogue.normalise("backup.keep_last", "many")


def test_catalogue_pins_and_python_values(
    make_descriptor: Callable[..., SettingDescriptor], pin: Pin
) -> None:
    """A pin is reported by key and a stored value converts to the setting's type."""
    cat = PydanticSettingsCatalogue(
        [],
        {},
        {},
    )
    with pytest.raises(UnknownSettingError):
        cat.pin("backup.keep_last")
    cat = PydanticSettingsCatalogue(
        [make_descriptor("backup.keep_last", 7)],
        {"backup.keep_last": TypeAdapter(Annotated[int, Field(ge=1)])},
        {"backup.keep_last": pin},
    )
    assert cat.pin("backup.keep_last") == pin
    assert cat.to_python("backup.keep_last", 5) == 5


async def test_repository_round_trips_and_isolates_owners(
    make_stored: Callable[..., StoredSetting],
) -> None:
    """Rows are addressed by scope, owner and key; callers get copies."""
    repo = InMemorySettingValueRepository()
    ann, bob = uuid7(), uuid7()
    row = make_stored("display.timezone", "UTC", ann, SettingScope.USER)
    await repo.save(row)
    await repo.save(
        make_stored("display.timezone", "Asia/Tokyo", bob, SettingScope.USER)
    )
    await repo.save(make_stored("backup.keep_last", 12))

    got = await repo.get(SettingScope.USER, ann, "display.timezone")
    assert got is not None
    assert got.value == "UTC"
    got.value = "mutated"
    again = await repo.get(SettingScope.USER, ann, "display.timezone")
    assert again is not None
    assert again.value == "UTC"

    assert set(await repo.list(SettingScope.INSTANCE, None)) == {"backup.keep_last"}
    assert set(await repo.list(SettingScope.USER, ann)) == {"display.timezone"}
    assert await repo.get(SettingScope.USER, uuid7(), "display.timezone") is None


async def test_repository_save_replaces_and_delete_reports(
    make_stored: Callable[..., StoredSetting],
) -> None:
    """Saving twice keeps one row; delete says whether anything was removed."""
    repo = InMemorySettingValueRepository()
    await repo.save(make_stored("backup.keep_last", 12))
    await repo.save(make_stored("backup.keep_last", 14))
    rows = await repo.list(SettingScope.INSTANCE, None)
    assert rows["backup.keep_last"].value == 14
    assert await repo.delete(SettingScope.INSTANCE, None, "backup.keep_last") is True
    assert await repo.delete(SettingScope.INSTANCE, None, "backup.keep_last") is False
