"""`ALL_SETTINGS` stays complete and agrees with the lists derived from it."""

from typing import get_type_hints

from app.platform.config import (
    ALL_SETTINGS,
    INSTANCE_SETTINGS,
    IdentityCliSettings,
    MenageristBaseSettings,
)
from app.platform.config._discovery import discover
from app.platform.config._fields import group_name, unwrap
from app.platform.config._markers import Public, Tunable


def _declared_settings() -> set[type[MenageristBaseSettings]]:
    """Every application settings class, found through subclassing."""
    found: set[type[MenageristBaseSettings]] = set()
    pending = list(MenageristBaseSettings.__subclasses__())
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        if cls.__module__.startswith("app."):
            found.add(cls)
    return found


def test_all_settings_lists_each_class_once() -> None:
    """A new settings class must be added to `ALL_SETTINGS` to reach the docs."""
    assert len(ALL_SETTINGS) == len(set(ALL_SETTINGS))
    assert set(ALL_SETTINGS) == _declared_settings()


def test_all_settings_is_the_instance_settings_plus_the_cli_only_class() -> None:
    """The server's getters and the CLI's class together make up every class."""
    served = {get_type_hints(getter)["return"] for getter in INSTANCE_SETTINGS}
    assert served | {IdentityCliSettings} == set(ALL_SETTINGS)
    assert served.isdisjoint({IdentityCliSettings})


def test_discovery_finds_every_marked_field_in_all_settings() -> None:
    """Discovery is the marked subset of `ALL_SETTINGS`; nothing marked is missed."""
    marked = {
        f"{group_name(cls)}.{name}"
        for cls in ALL_SETTINGS
        for name, field in cls.model_fields.items()
        if any(isinstance(m, Tunable | Public) for m in unwrap(field)[1])
    }
    assert {spec.key for spec in discover(ALL_SETTINGS)} == marked
