"""The collections a person shows on Home: a hidden, per-person list of ids."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.settings.adapters.platform.deployment_catalogue import build_catalogue
from app.modules.settings.domain.errors import InvalidSettingValueError
from app.modules.settings.domain.setting import SettingScope
from app.platform.config import HomeSettings
from app.platform.config._discovery import discover
from app.platform.config.home import MAX_HOME_COLLECTIONS

if TYPE_CHECKING:
    from app.modules.settings.adapters.platform.pydantic_settings_catalogue import (
        PydanticSettingsCatalogue,
    )

KEY = "home.collections"


def _catalogue() -> PydanticSettingsCatalogue:
    return build_catalogue(discover([HomeSettings]), {HomeSettings: HomeSettings()})


def _ids(count: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(count)]


def test_it_is_hidden_per_person_and_empty_by_default() -> None:
    """Changed from a collection page, so it is off Preferences and has no variable."""
    descriptor = _catalogue().descriptor(KEY)

    assert descriptor.scope is SettingScope.USER
    assert descriptor.hidden
    assert descriptor.env_name is None
    assert descriptor.default == []


def test_the_environment_never_sets_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """A variable of the same name is ignored: there is no deployment default."""
    monkeypatch.setenv("MENAGERIST_HOME_COLLECTIONS", f'["{uuid.uuid4()}"]')
    catalogue = _catalogue()

    assert catalogue.descriptor(KEY).default == []
    assert not catalogue.descriptor(KEY).default_from_env


def test_a_list_of_ids_up_to_the_limit_is_kept_in_order() -> None:
    """Order is the order the collections were added."""
    ids = _ids(MAX_HOME_COLLECTIONS)

    assert _catalogue().normalise(KEY, ids) == ids


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (["not-an-id"], "pattern"),
        (_ids(MAX_HOME_COLLECTIONS + 1), "at most 50"),
        ([(same := str(uuid.uuid4())), same], "more than once"),
        ([(lower := str(uuid.uuid4())), lower.upper()], "more than once"),
        ("not a list", "list"),
    ],
)
def test_a_bad_list_is_refused(value: object, reason: str) -> None:
    """Non-ids, too many and repeats are refused before anything is saved."""
    with pytest.raises(InvalidSettingValueError, match=reason):
        _catalogue().normalise(KEY, value)
