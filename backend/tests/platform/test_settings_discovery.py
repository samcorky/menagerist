import json
from collections.abc import Callable  # noqa: TC003 - pydantic resolves this at runtime
from enum import StrEnum
from typing import Annotated
from zoneinfo import ZoneInfo

import pytest
from pydantic import AliasChoices, Field, SecretStr, ValidationError

from app.platform.config import SETTING_GROUPS, MenageristBaseSettings
from app.platform.config._discovery import (
    SettingDeclarationError,
    SettingSpec,
    discover,
)
from app.platform.config._markers import Public, Scope, Tunable, UIMeta
from app.platform.config._types import Cron, Hours  # noqa: TC001 - pydantic resolves these at runtime
from app.platform.shared_data import shared_data_path

KINDS = frozenset({"cron"})


class Mode(StrEnum):
    """A choice for the enumeration setting."""

    FAST = "fast"
    SLOW = "slow"


type Tuned = Annotated[int, Field(ge=1), UIMeta(unit="minutes"), Tunable()]


class ExampleSettings(MenageristBaseSettings):
    """A group exercising every way a field can be declared."""

    plain: int = Field(default=1, title="Plain", description="Not tunable.")
    direct: Annotated[int, Field(ge=1), Tunable()] = Field(
        default=7, title="Direct", description="Tunable through Annotated."
    )
    aliased: Annotated[Hours, Tunable(restart_required=True)] = Field(
        default=24, title="Aliased", description="Tunable through a type alias."
    )
    nested: Tuned = Field(
        default=5, title="Nested", description="Marker inside the alias."
    )
    schedule: Annotated[Cron, Tunable()] = Field(
        default="0 3 * * *",
        validation_alias="MENAGERIST_EXAMPLE_SCHEDULE",
        title="Schedule",
        description="A cron expression.",
    )
    choice: Annotated[Mode, Tunable()] = Field(
        default=Mode.FAST,
        validation_alias=AliasChoices("MENAGERIST_EXAMPLE_CHOICE", "EXAMPLE_CHOICE"),
        title="Choice",
        description="An enumeration.",
    )
    names: Annotated[list[str], Tunable()] = Field(
        default_factory=list, title="Names", description="A list of strings."
    )
    shown: Annotated[bool, Public()] = Field(
        default=True, title="Shown", description="Public but not tunable."
    )


@pytest.fixture(scope="module")
def specs() -> dict[str, SettingSpec]:
    """Discover the example group once."""
    return {spec.key: spec for spec in discover([ExampleSettings], kinds=KINDS)}


def test_only_marked_fields_are_discovered(specs: dict[str, SettingSpec]) -> None:
    """Only marked fields are discovered."""
    assert set(specs) == {
        "example.direct",
        "example.aliased",
        "example.nested",
        "example.schedule",
        "example.choice",
        "example.names",
        "example.shown",
    }


def test_key_group_and_scope(specs: dict[str, SettingSpec]) -> None:
    """Key group and scope."""
    spec = specs["example.direct"]
    assert (spec.group, spec.field_name, spec.scope) == (
        "example",
        "direct",
        Scope.INSTANCE,
    )
    assert spec.tunable
    assert not spec.public


def test_markers_are_found_through_aliases(specs: dict[str, SettingSpec]) -> None:
    """Markers are found through aliases."""
    assert specs["example.aliased"].restart_required
    assert specs["example.nested"].tunable
    assert not specs["example.direct"].restart_required


def test_public_only_field_is_not_tunable(specs: dict[str, SettingSpec]) -> None:
    """Public only field is not tunable."""
    spec = specs["example.shown"]
    assert spec.public
    assert not spec.tunable
    assert spec.scope is None


def test_env_names(specs: dict[str, SettingSpec]) -> None:
    """Env names."""
    assert specs["example.direct"].env_name == "MENAGERIST_DIRECT"
    assert specs["example.schedule"].env_name == "MENAGERIST_EXAMPLE_SCHEDULE"
    assert specs["example.choice"].env_name == "MENAGERIST_EXAMPLE_CHOICE"


def test_schema_carries_constraints_hints_and_text(
    specs: dict[str, SettingSpec],
) -> None:
    """Schema carries constraints hints and text."""
    aliased = specs["example.aliased"].schema
    assert aliased["type"] == "integer"
    assert aliased["exclusiveMinimum"] == 0
    assert aliased["x-menagerist"] == {"unit": "hours"}
    assert aliased["title"] == "Aliased"
    assert aliased["description"] == "Tunable through a type alias."
    assert aliased["default"] == 24
    assert specs["example.schedule"].schema["x-menagerist"] == {"kind": "cron"}
    assert "x-menagerist" not in specs["example.direct"].schema


def test_schema_does_not_leak_server_markers(specs: dict[str, SettingSpec]) -> None:
    """Schema does not leak server markers."""
    assert "restart_required" not in json.dumps(specs["example.aliased"].schema)


def test_default_is_json_ready(specs: dict[str, SettingSpec]) -> None:
    """Default is json ready."""
    assert specs["example.choice"].default == "fast"
    assert specs["example.names"].default == []


def test_ui_meta_rejects_unknown_hint_names() -> None:
    """Ui meta rejects unknown hint names."""
    with pytest.raises(TypeError):
        UIMeta(colour="red")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("annotation", "default"),
    [
        (int | None, None),
        (list[int], []),
    ],
)
def test_non_primitive_tunables_are_rejected(
    annotation: object, default: object
) -> None:
    """Non primitive tunables are rejected."""

    class Bad(MenageristBaseSettings):
        value: Annotated[annotation, Tunable()] = Field(  # type: ignore[valid-type]
            default=default, title="Value", description="Bad."
        )

    with pytest.raises(SettingDeclarationError, match="flat primitive"):
        discover([Bad], kinds=KINDS)


def test_public_secret_is_rejected() -> None:
    """Public secret is rejected."""

    class Bad(MenageristBaseSettings):
        token: Annotated[SecretStr, Public()] = Field(
            default=SecretStr("x"), title="Token", description="Secret."
        )

    with pytest.raises(SettingDeclarationError, match="secret"):
        discover([Bad], kinds=KINDS)


def test_tunable_needs_a_title() -> None:
    """Tunable needs a title."""

    class Bad(MenageristBaseSettings):
        value: Annotated[int, Tunable()] = Field(default=1, description="Untitled.")

    with pytest.raises(SettingDeclarationError, match="title"):
        discover([Bad], kinds=KINDS)


def test_unlisted_kind_is_rejected() -> None:
    """Unlisted kind is rejected."""

    class Bad(MenageristBaseSettings):
        value: Annotated[str, UIMeta(kind="mystery"), Tunable()] = Field(
            default="", title="Value", description="Odd kind."
        )

    with pytest.raises(SettingDeclarationError, match="mystery"):
        discover([Bad], kinds=KINDS)


def test_duplicate_keys_are_rejected() -> None:
    """Duplicate keys are rejected."""
    with pytest.raises(SettingDeclarationError, match="duplicate"):
        discover([ExampleSettings, ExampleSettings], kinds=KINDS)


def test_registered_groups_pass_registration_guards() -> None:
    """Registered groups pass registration guards."""
    contract = json.loads(
        shared_data_path("contracts/field-kinds.json").read_text(encoding="utf-8")
    )
    specs = discover(SETTING_GROUPS, kinds=frozenset(contract["kinds"]))
    assert {spec.key for spec in specs} >= {
        "backup.schedule",
        "backup.keep_last",
        "backup.user_export_ttl_hours",
        "scheduler.run_history_per_job",
    }
    assert all(spec.title for spec in specs)


def test_adapter_keeps_field_constraints(specs: dict[str, SettingSpec]) -> None:
    """Validating with the bare annotation would accept 0 for a `ge=1` field."""
    assert specs["example.direct"].adapter.validate_python(3) == 3
    with pytest.raises(ValidationError):
        specs["example.direct"].adapter.validate_python(0)
    with pytest.raises(ValidationError):
        specs["example.aliased"].adapter.validate_python(0)


def test_ui_meta_merges_all_hints_and_skips_when_empty() -> None:
    """Ui meta merges all hints and skips when empty."""
    from pydantic import TypeAdapter

    hinted = TypeAdapter(Annotated[str, UIMeta(kind="cron", display="words")])
    assert hinted.json_schema()["x-menagerist"] == {"kind": "cron", "display": "words"}
    assert "x-menagerist" not in TypeAdapter(Annotated[str, UIMeta()]).json_schema()


def test_group_name_is_snake_case() -> None:
    """Group name is snake case."""
    from app.platform.config._discovery import group_name

    class ApiTokenSettings(MenageristBaseSettings): ...

    assert group_name(ApiTokenSettings) == "api_token"


def test_zoneinfo_is_stored_as_a_string_and_read_back_as_a_zone() -> None:
    """A rich type qualifies when it is stored as one JSON scalar."""

    class Zoned(MenageristBaseSettings):
        zone: Annotated[ZoneInfo, Tunable(scope=Scope.USER)] = Field(
            default=ZoneInfo("UTC"), title="Timezone", description="Display zone."
        )

    (spec,) = discover([Zoned], kinds=KINDS)
    assert spec.default == "UTC"
    assert spec.schema["type"] == "string"
    assert spec.adapter.validate_python("Europe/London") == ZoneInfo("Europe/London")
    assert spec.adapter.dump_python(ZoneInfo("Europe/London"), mode="json") == (
        "Europe/London"
    )
    with pytest.raises(ValidationError):
        spec.adapter.validate_python("Not/AZone")


def test_type_without_a_json_schema_is_rejected() -> None:
    """A tunable must be describable, so the form can render it."""

    class Bad(MenageristBaseSettings):
        value: Annotated[Callable[[], None], Tunable()] = Field(
            default=lambda: None, title="Value", description="Not describable."
        )

    with pytest.raises(SettingDeclarationError, match="JSON Schema"):
        discover([Bad], kinds=KINDS)
