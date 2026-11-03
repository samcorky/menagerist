"""Describe the settings fields that are tunable or public, from their annotations."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import AnyUrl, SecretBytes, SecretStr, TypeAdapter
from pydantic.errors import PydanticInvalidForJsonSchema
from pydantic.fields import FieldInfo
from pydantic_core import MultiHostUrl

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._fields import (
    JsonObject,
    env_name,
    field_adapter,
    group_name,
    inline_schema,
    unwrap,
)
from app.platform.config._markers import Public, Scope, Tunable

if TYPE_CHECKING:
    from collections.abc import Iterable

_FLAT_JSON_TYPES = frozenset({"boolean", "integer", "number", "string"})
_SECRET = (SecretStr, SecretBytes)
_CREDENTIAL_URL = (AnyUrl, MultiHostUrl)


class SettingDeclarationError(ValueError):
    """A settings field is marked in a way the settings module cannot honour."""


@dataclass(frozen=True, kw_only=True)
class SettingSpec:
    """One marked field: identity, markers, JSON Schema and how to validate it."""

    key: str
    group: str
    field_name: str
    group_type: type[MenageristBaseSettings]
    field: FieldInfo
    title: str
    description: str | None
    scope: Scope | None
    restart_required: bool
    public: bool
    env_name: str
    default: object
    schema: JsonObject

    @property
    def tunable(self) -> bool:
        """Whether an admin or user may change the value at runtime."""
        return self.scope is not None

    @property
    def adapter(self) -> TypeAdapter[object]:
        """Validate a stored value with the field's own constraints.

        The annotation alone drops constraints such as `ge=1`; they live in the
        field's metadata.
        """
        return field_adapter(self.field)


def _is_flat(schema: JsonObject) -> bool:
    """Whether a value is stored as one JSON scalar or a list of strings."""
    kind = schema.get("type")
    if kind in _FLAT_JSON_TYPES:
        return True
    return kind == "array" and schema.get("items", {}).get("type") == "string"


def _reject_sensitive(label: str, base: object) -> None:
    if base in _SECRET:
        msg = f"{label}: a secret cannot be tunable or public"
        raise SettingDeclarationError(msg)
    if isinstance(base, type) and issubclass(base, _CREDENTIAL_URL):
        msg = f"{label}: a URL may embed credentials, so it cannot be tunable or public"
        raise SettingDeclarationError(msg)


def _spec(
    group_type: type[MenageristBaseSettings],
    name: str,
    kinds: frozenset[str] | None,
) -> SettingSpec | None:
    field = group_type.model_fields[name]
    base, markers = unwrap(field)
    tunable = next((m for m in markers if isinstance(m, Tunable)), None)
    public = any(isinstance(m, Public) for m in markers)
    if tunable is None and not public:
        return None

    label = f"{group_type.__name__}.{name}"
    _reject_sensitive(label, base)
    if not field.title:
        msg = f"{label}: add Field(title=...) so the setting can be labelled"
        raise SettingDeclarationError(msg)

    adapter: TypeAdapter[object] = field_adapter(field)
    try:
        schema = inline_schema(adapter.json_schema(by_alias=False))
    except PydanticInvalidForJsonSchema as exc:
        msg = f"{label}: no JSON Schema for {base!r}; give it WithJsonSchema"
        raise SettingDeclarationError(msg) from exc
    if tunable is not None and not _is_flat(schema):
        msg = (
            label
            + ": a tunable must be a flat primitive "
            + f"(one JSON scalar or a list of strings), not {base!r}"
        )
        raise SettingDeclarationError(msg)
    schema["title"] = field.title
    if field.description:
        schema["description"] = field.description
    default = adapter.dump_python(
        field.get_default(call_default_factory=True), mode="json"
    )
    schema["default"] = default

    kind = schema.get("x-menagerist", {}).get("kind")
    if kinds is not None and kind is not None and kind not in kinds:
        msg = f"{label}: the field kind {kind!r} is not in the field-kinds contract"
        raise SettingDeclarationError(msg)

    group = group_name(group_type)
    return SettingSpec(
        key=f"{group}.{name}",
        group=group,
        field_name=name,
        group_type=group_type,
        field=field,
        title=field.title,
        description=field.description,
        scope=tunable.scope if tunable else None,
        restart_required=tunable.restart_required if tunable else False,
        public=public,
        env_name=env_name(group_type, name),
        default=default,
        schema=schema,
    )


def discover(
    groups: Iterable[type[MenageristBaseSettings]],
    *,
    kinds: frozenset[str] | None = None,
) -> list[SettingSpec]:
    """List every `Tunable` or `Public` field, failing on a bad declaration.

    Args:
        groups: Settings classes to inspect.
        kinds: UI field kinds the frontend knows; any other hint is an error. When
            omitted the kinds are not checked (the contract lives with the tests).
    """
    specs: dict[str, SettingSpec] = {}
    for group_type in groups:
        for name in group_type.model_fields:
            spec = _spec(group_type, name, kinds)
            if spec is None:
                continue
            if spec.key in specs:
                msg = f"duplicate setting key {spec.key}"
                raise SettingDeclarationError(msg)
            specs[spec.key] = spec
    return list(specs.values())
