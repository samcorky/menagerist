"""Read a settings field's group, environment name, annotations and validator.

Shared by every walker over the settings classes: the tunable-field discovery and the
generated reference.
"""

import re
from typing import TYPE_CHECKING, Annotated, Any, TypeAliasType, get_args, get_origin

from pydantic import AliasChoices, TypeAdapter

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

    from app.platform.config._base import MenageristBaseSettings

# JSON Schema is an open-ended document; its members have no useful static type.
type JsonObject = dict[str, Any]


def group_name(group_type: type[MenageristBaseSettings]) -> str:
    """The declared group, else the class name: `ApiTokenSettings` is `api_token`."""
    if group_type.group is not None:
        return group_type.group
    name = group_type.__name__.removesuffix("Settings")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def unwrap(field: FieldInfo) -> tuple[object, list[object]]:
    """Return the underlying type and every annotation, through `type` aliases."""
    markers = list(field.metadata)
    current: object = field.annotation
    while True:
        if isinstance(current, TypeAliasType):
            current = current.__value__
        elif get_origin(current) is Annotated:
            origin, *metadata = get_args(current)
            markers.extend(metadata)
            current = origin
        else:
            return current, markers


def env_name(group_type: type[MenageristBaseSettings], name: str) -> str:
    """The environment variable a field reads, honouring a string alias."""
    alias = group_type.model_fields[name].validation_alias
    if isinstance(alias, AliasChoices):
        alias = next((c for c in alias.choices if isinstance(c, str)), None)
    if isinstance(alias, str):
        return alias.upper()
    prefix = group_type.model_config.get("env_prefix", "")
    return f"{prefix}{name}".upper()


def env_aliases(group_type: type[MenageristBaseSettings], name: str) -> tuple[str, ...]:
    """The other environment variables a field also reads, after `env_name`."""
    alias = group_type.model_fields[name].validation_alias
    if not isinstance(alias, AliasChoices):
        return ()
    names = [c.upper() for c in alias.choices if isinstance(c, str)]
    return tuple(n for n in names[1:] if n != env_name(group_type, name))


def field_adapter[T](field: FieldInfo) -> TypeAdapter[T]:
    """Validate a value with the field's own constraints.

    The annotation alone drops constraints such as `ge=1`; they live in the field's
    metadata. `T` is the field's value type, which only the caller knows.
    """
    annotation: type[T] = field.annotation  # type: ignore[assignment]
    if field.metadata:
        annotation = Annotated[annotation, *field.metadata]  # type: ignore[assignment]
    return TypeAdapter(annotation)


def inline_schema(schema: JsonObject) -> JsonObject:
    """Replace a top-level `$ref` with its definition and drop `$defs`."""
    definitions = schema.get("$defs", {})
    while "$ref" in schema:
        target = definitions[schema["$ref"].rsplit("/", 1)[-1]]
        schema = {**target, **{k: v for k, v in schema.items() if k != "$ref"}}
    return {k: v for k, v in schema.items() if k != "$defs"}
