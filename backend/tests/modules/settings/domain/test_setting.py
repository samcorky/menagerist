from collections.abc import Callable
from uuid import uuid7

import pytest

from app.modules.settings.domain.errors import (
    InvalidSettingValueError,
    SettingLockedError,
    UnknownSettingError,
)
from app.modules.settings.domain.setting import (
    Pin,
    SettingDescriptor,
    SettingScope,
    SettingSource,
    StoredSetting,
    resolve,
)

type DescriptorFactory = Callable[..., SettingDescriptor]


def _valid(_: object) -> bool:
    return True


def _invalid(_: object) -> bool:
    return False


def test_a_pin_wins_over_a_stored_value_and_locks(
    make_descriptor: DescriptorFactory,
) -> None:
    """The deployment's value is final, whatever an administrator saved."""
    pin = Pin(env_name="MENAGERIST_BACKUP_KEEP_LAST", value=30)
    got = resolve(
        make_descriptor("backup.keep_last", 7), pin=pin, stored=12, is_valid=_valid
    )
    assert (got.value, got.source, got.locked) == (30, SettingSource.ENV, True)
    assert got.env_name == "MENAGERIST_BACKUP_KEEP_LAST"


def test_a_valid_stored_value_beats_the_default(
    make_descriptor: DescriptorFactory,
) -> None:
    """An instance value is attributed to the instance layer."""
    got = resolve(
        make_descriptor("backup.keep_last", 7), pin=None, stored=12, is_valid=_valid
    )
    assert (got.value, got.source, got.locked) == (12, SettingSource.INSTANCE, False)


def test_a_user_value_is_attributed_to_the_user_layer(
    make_descriptor: DescriptorFactory,
) -> None:
    """The source names the layer that supplied the value."""
    d = make_descriptor("display.timezone", "UTC", SettingScope.USER)
    got = resolve(d, pin=None, stored="Europe/London", is_valid=_valid)
    assert (got.value, got.source) == ("Europe/London", SettingSource.USER)


def test_the_default_applies_when_nothing_is_saved(
    make_descriptor: DescriptorFactory,
) -> None:
    """No pin and no row means the code default."""
    got = resolve(
        make_descriptor("backup.keep_last", 7), pin=None, stored=None, is_valid=_valid
    )
    assert (got.value, got.source, got.stored_invalid) == (
        7,
        SettingSource.DEFAULT,
        False,
    )


def test_an_invalid_stored_value_falls_back_and_is_flagged(
    make_descriptor: DescriptorFactory,
) -> None:
    """A tightened constraint must not crash a reader."""
    got = resolve(
        make_descriptor("backup.keep_last", 7), pin=None, stored=0, is_valid=_invalid
    )
    assert (got.value, got.source, got.stored_invalid) == (
        7,
        SettingSource.DEFAULT,
        True,
    )


def test_instance_rows_have_no_owner_and_user_rows_need_one(
    make_descriptor: DescriptorFactory,
) -> None:
    """The owner column follows the scope."""
    row = StoredSetting.create(
        scope=SettingScope.INSTANCE, owner_id=None, key="a.b", value=1, updated_by=None
    )
    assert row.owner_id is None
    with pytest.raises(ValueError, match="needs an owner"):
        StoredSetting.create(
            scope=SettingScope.USER, owner_id=None, key="a.b", value=1, updated_by=None
        )
    with pytest.raises(ValueError, match="needs an owner"):
        StoredSetting.create(
            scope=SettingScope.INSTANCE,
            owner_id=uuid7(),
            key="a.b",
            value=1,
            updated_by=None,
        )


def test_change_records_who_and_when(make_descriptor: DescriptorFactory) -> None:
    """Saving a new value touches the audit fields."""
    row = StoredSetting.create(
        scope=SettingScope.INSTANCE, owner_id=None, key="a.b", value=1, updated_by=None
    )
    before, editor = row.updated_at, uuid7()
    row.change(2, editor)
    assert (row.value, row.updated_by) == (2, editor)
    assert row.updated_at >= before


def test_errors_carry_their_key_and_map_to_http_base_types(
    make_descriptor: DescriptorFactory,
) -> None:
    """The shared handlers turn the base types into 404, 409 and 400."""
    from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError

    assert isinstance(UnknownSettingError("x"), NotFoundError)
    locked = SettingLockedError("x", "MENAGERIST_X")
    assert isinstance(locked, ConflictError)
    assert "MENAGERIST_X" in str(locked)
    assert isinstance(InvalidSettingValueError("x", "too small"), ValidationError)
