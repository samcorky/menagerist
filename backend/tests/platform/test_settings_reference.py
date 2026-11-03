"""The generated `.env.example` and `docs/settings.md` match the settings classes."""

import io
import os
from collections.abc import Callable  # noqa: TC003 - pydantic resolves this at runtime
from typing import Literal

import pytest
from dotenv import dotenv_values
from pydantic import Field, PostgresDsn, SecretStr

from app.platform.config import ALL_SETTINGS, MenageristBaseSettings
from app.platform.config._reference import (
    build_sections,
    reference_files,
    render_env_example,
    render_settings_doc,
)
from app.platform.config._types import Cron, Origin, ProxyAddress, StarOrCSV  # noqa: TC001 - pydantic resolves these at runtime


class Demo(MenageristBaseSettings, group="demo"):
    """Settings covering each special case the reference handles."""

    proxies: StarOrCSV[ProxyAddress] = Field(
        default=["10.0.0.0/8", "192.168.0.0/16"], description="Trusted proxies."
    )
    origins: StarOrCSV[Origin] = Field(default=[], description="Allowed origins.")
    schedule: Cron = Field(default="0 3 * * *", description="When to run.")
    note: str | None = Field(default=None, description="An optional note.")
    enabled: bool = Field(default=True, description="Whether it is on.")
    count: int = Field(default=3, description="Any whole number.")
    ceiling: int = Field(default=1, le=10, description="At most ten.")
    mode: Literal["fast", "slow"] = Field(default="fast", description="Which mode.")
    token: SecretStr = Field(default=SecretStr("hunter2"), description="A secret.")
    dsn: PostgresDsn = Field(
        default=PostgresDsn("postgresql://user:s3cret@db.example/app"),
        description="A database URL.",
    )


class Opaque(MenageristBaseSettings, group="opaque"):
    """A field type that has no JSON Schema."""

    hook: Callable[[str], int] | None = Field(default=None, description="A callable.")


def _demo() -> dict[str, str]:
    return {
        line.split("=", 1)[0].removeprefix("# "): line.split("=", 1)[1]
        for line in render_env_example(build_sections([Demo])).splitlines()
        if line.startswith(("# MENAGERIST_DEMO_", "MENAGERIST_DEMO_"))
    }


def test_lists_are_comma_joined_and_an_empty_list_is_empty() -> None:
    """A CSV default is written as one comma-separated value."""
    lines = _demo()
    assert lines["MENAGERIST_DEMO_PROXIES"] == "10.0.0.0/8,192.168.0.0/16"
    assert lines["MENAGERIST_DEMO_ORIGINS"] == ""


def test_values_with_spaces_are_quoted_and_plain_values_are_not() -> None:
    """A cron expression holds spaces and `*`, so it is quoted for a dotenv reader."""
    lines = _demo()
    assert lines["MENAGERIST_DEMO_SCHEDULE"] == '"0 3 * * *"'
    assert lines["MENAGERIST_DEMO_MODE"] == "fast"
    assert lines["MENAGERIST_DEMO_ENABLED"] == "true"


def test_an_unset_default_is_left_blank() -> None:
    """`None` has no value to write."""
    assert _demo()["MENAGERIST_DEMO_NOTE"] == ""


@pytest.mark.parametrize("secret", ["hunter2", "s3cret"])
def test_secret_and_credential_defaults_are_never_written(secret: str) -> None:
    """Neither output carries a secret default or a database password."""
    sections = build_sections([Demo])
    for text in (render_env_example(sections), render_settings_doc(sections)):
        assert secret not in text


def test_a_sensitive_variable_is_marked_and_blank() -> None:
    """The secret and the URL are commented blank; the reference masks the URL."""
    lines = _demo()
    assert lines["MENAGERIST_DEMO_TOKEN"] == ""
    assert lines["MENAGERIST_DEMO_DSN"] == ""
    doc = render_settings_doc(build_sections([Demo]))
    assert "none (sensitive)" in doc
    assert "`postgresql://user:***@db.example/app`" in doc


def test_enabled_uncomments_only_variables_that_have_a_value() -> None:
    """Sensitive and unset variables stay commented even when defaults are enabled."""
    text = render_env_example(build_sections([Demo]), enabled=True)
    active = {
        line.split("=", 1)[0]
        for line in text.splitlines()
        if "=" in line and not line.startswith("#")
    }
    assert "MENAGERIST_DEMO_PROXIES" in active
    assert not active & {
        "MENAGERIST_DEMO_TOKEN",
        "MENAGERIST_DEMO_DSN",
        "MENAGERIST_DEMO_NOTE",
    }


def test_the_reference_describes_type_and_allowed_values() -> None:
    """Choices, lists, schedules and bounds are spelled out in the table."""
    doc = render_settings_doc(build_sections([Demo]))
    assert "| `MENAGERIST_DEMO_MODE` | text | `fast` | `fast`, `slow` |" in doc
    assert "comma-separated list of IP addresses or networks" in doc
    assert "`*` on its own" in doc
    assert "cron schedule" in doc


def test_an_unbounded_number_has_no_allowed_range() -> None:
    """With no bounds there is nothing to add to the allowed values."""
    entries = {e.env_name: e for s in build_sections([Demo]) for e in s.entries}
    assert entries["MENAGERIST_DEMO_COUNT"].type_label == "whole number"
    assert entries["MENAGERIST_DEMO_COUNT"].allowed == ""
    assert entries["MENAGERIST_DEMO_CEILING"].allowed == "10 or less"


def test_a_type_without_a_json_schema_is_listed_as_text() -> None:
    """The reference still lists the variable when pydantic cannot describe it."""
    (section,) = build_sections([Opaque])
    (entry,) = section.entries
    assert (entry.type_label, entry.allowed, entry.default) == ("text", "", None)


def test_every_field_of_every_class_is_listed_once() -> None:
    """Deployment-only variables are included, not just tunable or public ones."""
    listed = [e.env_name for s in build_sections(ALL_SETTINGS) for e in s.entries]
    assert len(listed) == len(set(listed))
    assert "MENAGERIST_MEDIA_STORAGE_PATH" in listed
    assert "MENAGERIST_API_TRUSTED_PROXIES" in listed
    assert "MENAGERIST_IDENTITY_INITIAL_PASSWORD" in listed
    assert len(listed) == sum(len(cls.model_fields) for cls in ALL_SETTINGS)


def test_classes_sharing_a_group_share_a_section() -> None:
    """`IdentitySettings` and the CLI-only class both read `MENAGERIST_IDENTITY_*`."""
    groups = [section.group for section in build_sections(ALL_SETTINGS)]
    assert groups.count("identity") == 1


def test_an_alias_is_shown_as_another_way_to_set_the_variable() -> None:
    """The instance timezone is also read from `TZ`."""
    entries = {e.env_name: e for s in build_sections(ALL_SETTINGS) for e in s.entries}
    assert entries["MENAGERIST_TIMEZONE"].aliases == ("TZ",)
    assert "Also read from `TZ`" in render_settings_doc(build_sections(ALL_SETTINGS))


def test_the_database_password_is_withheld_from_the_real_reference() -> None:
    """The shipped database default carries a password, which must not be written."""
    for text in reference_files(ALL_SETTINGS).values():
        assert "menagerist:menagerist@" not in text


def test_the_defaults_in_the_env_file_load_back_as_the_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uncomment every default, load it through each class, and nothing changes.

    This catches a default that is rendered in a form its own validator refuses, such
    as an origin that normalises differently or a list that does not split back.
    """
    for name in ("TZ", *(k for k in os.environ if k.startswith("MENAGERIST_"))):
        monkeypatch.delenv(name, raising=False)
    defaults = {cls: cls().model_dump() for cls in ALL_SETTINGS}

    sections = build_sections(ALL_SETTINGS)
    env = dotenv_values(stream=io.StringIO(render_env_example(sections, enabled=True)))
    expected = [e for s in sections for e in s.entries if e.default is not None]
    assert set(env) == {e.env_name for e in expected}
    for name, value in env.items():
        monkeypatch.setenv(name, value or "")

    for cls in ALL_SETTINGS:
        assert cls().model_dump() == defaults[cls], cls.__name__
