"""Describe every deployment setting and render the generated reference files.

Unlike `_discovery`, which keeps only the tunable and public fields for the settings
page, this walks every field of every settings class, so deployment-only variables
such as the media storage path are included. Secrets and credential URLs never have
their defaults written out.
"""

import re
import textwrap
from dataclasses import dataclass
from types import UnionType
from typing import TYPE_CHECKING, Annotated, TypeAliasType, Union, get_args, get_origin

from pydantic import AnyUrl, SecretBytes, SecretStr, TypeAdapter
from pydantic.errors import PydanticInvalidForJsonSchema
from pydantic_core import MultiHostUrl

from app.platform.config._compose import (
    COMPOSE_GROUP,
    COMPOSE_SUMMARY,
    DESCRIPTIONS,
    check_descriptions,
    compose_defaults,
)
from app.platform.config._fields import (
    JsonObject,
    env_aliases,
    env_name,
    field_adapter,
    group_name,
    unwrap,
)
from app.platform.config._markers import Internal, Tunable
from app.platform.config.dsn import mask_dsn

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

    from pydantic.fields import FieldInfo

    from app.platform.config._base import MenageristBaseSettings

ENV_EXAMPLE_PATH = ".env.example"
SETTINGS_DOC_PATH = "docs/settings.md"

_WIDTH = 88
_ACRONYMS = {"api": "API"}
_INTRO = (
    "Every deployment setting is an environment variable. Put the ones you change in a "
    + "`.env` file next to `compose.yaml`; "
    + f"[`{ENV_EXAMPLE_PATH}`](../{ENV_EXAMPLE_PATH}) lists them all with their "
    + "defaults. A list is comma-separated, and a sensitive value (a secret or a URL "
    + "with credentials) has no default here."
)
# Set by the Dockerfile, so a container differs from the defaults below. A test checks
# the Dockerfile still sets each of these.
IMAGE_VALUES = {
    "MENAGERIST_API_FRONTEND_DIST_PATH": "/app/frontend",
    "MENAGERIST_SERVER_IN_CONTAINER": "1",
}
_IMAGE_NOTE = (
    "The Docker image sets "
    + " and ".join(f"`{name}={value}`" for name, value in IMAGE_VALUES.items())
    + " itself, so in a container those two differ from the defaults listed here."
)
_SENSITIVE = (SecretStr, SecretBytes, AnyUrl, MultiHostUrl)
_UNSAFE_IN_DOTENV = re.compile(r"[^\w./:@,+-]")

# Named types in a JSON Schema reference, as (singular, plural) wording.
_NAMED_TYPES = {
    "Origin": ("origin", "origins"),
    "ProxyAddress": ("IP address or network", "IP addresses or networks"),
}
# JSON Schema formats of values that hold secrets or may embed credentials. Pydantic's
# `PostgresDsn` is not a `MultiHostUrl` subclass, so the Python types alone miss it.
_SENSITIVE_FORMATS = frozenset({"password", "multi-host-uri"})
_FORMAT_TYPES = {
    "path": "path",
    "zoneinfo": "time zone (IANA name)",
    "password": "secret",
    "multi-host-uri": "database URL",
}
_JSON_TYPES = {"boolean": "true or false", "integer": "whole number", "string": "text"}


@dataclass(frozen=True, kw_only=True)
class SettingEntry:
    """One environment variable: how it is read, typed, defaulted and described."""

    env_name: str
    aliases: tuple[str, ...]
    group: str
    type_label: str
    allowed: str
    description: str
    default: str | None
    """The value to write; `None` when unset or withheld because it is sensitive."""
    shown_default: str | None
    """A safe rendering of a sensitive default (a masked URL), if one exists."""
    sensitive: bool
    tunable: bool
    restart_required: bool


@dataclass(frozen=True, kw_only=True)
class SettingsSection:
    """The settings of one group, which may span several classes."""

    group: str
    summary: str
    entries: tuple[SettingEntry, ...]


def _leaves(tp: object) -> Iterator[object]:
    """Yield the concrete types inside aliases, `Annotated` and unions."""
    if isinstance(tp, TypeAliasType):
        yield from _leaves(tp.__value__)
    elif get_origin(tp) is Annotated:
        yield from _leaves(get_args(tp)[0])
    elif get_origin(tp) in (Union, UnionType):
        for member in get_args(tp):
            yield from _leaves(member)
    else:
        yield tp


def _sensitive_schema(schema: JsonObject) -> bool:
    members = [
        *schema.get("anyOf", []),
        *([schema["items"]] if "items" in schema else []),
    ]
    return schema.get("format") in _SENSITIVE_FORMATS or any(
        _sensitive_schema(member) for member in members
    )


def _is_sensitive(field: FieldInfo, schema: JsonObject) -> bool:
    """Whether the field holds a secret or a URL that may embed credentials."""
    base, _ = unwrap(field)
    return _sensitive_schema(schema) or any(
        isinstance(leaf, type) and issubclass(leaf, _SENSITIVE)
        for leaf in _leaves(base)
    )


def group_title(group: str) -> str:
    """Title-case a group name for a heading, keeping acronyms upper-case."""
    return _ACRONYMS.get(group, group.title())


def _code(text: str) -> str:
    """Inline code, widening the fence when the text itself holds a backtick."""
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def _bounds(schema: JsonObject) -> str:
    low, above = schema.get("minimum"), schema.get("exclusiveMinimum")
    high = schema.get("maximum")
    if low is not None and high is not None:
        return f"{low} to {high}"
    if low is not None:
        return f"{low} or more"
    if above is not None:
        return f"more than {above}"
    if high is not None:
        return f"{high} or less"
    return ""


def _describe(
    schema: JsonObject, *, plural: bool = False
) -> tuple[list[str], list[str]]:
    """Return the type words and allowed-value phrases of a JSON Schema."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        singular, many = _NAMED_TYPES.get(name, (name.lower(), f"{name.lower()}s"))
        return [many if plural else singular], []
    if "anyOf" in schema:
        types: list[str] = []
        allowed: list[str] = []
        for member in schema["anyOf"]:
            if member.get("type") != "null":
                member_types, member_allowed = _describe(member, plural=plural)
                types += member_types
                allowed += member_allowed
        return list(dict.fromkeys(types)), allowed
    if "const" in schema:
        return [], [f"`{schema['const']}`"]
    if "enum" in schema:
        return ["text"], [f"`{value}`" for value in schema["enum"]]
    if schema.get("type") == "array":
        types, allowed = _describe(schema.get("items", {}), plural=True)
        label = f"comma-separated list of {' or '.join(types) or 'text'}"
        return [label], [f"{item} on its own" for item in allowed]
    return _describe_scalar(schema)


def _describe_scalar(schema: JsonObject) -> tuple[list[str], list[str]]:
    hints = schema.get("x-menagerist", {})
    allowed: list[str] = []
    if hints.get("kind") == "cron":
        return ["cron schedule"], ["five fields; empty turns the job off"]
    label = _FORMAT_TYPES.get(
        schema.get("format", ""), _JSON_TYPES.get(schema.get("type", ""), "text")
    )
    if hints.get("unit"):
        label = f"{label} ({hints['unit']})"
    if bounds := _bounds(schema):
        allowed.append(bounds)
    if pattern := schema.get("pattern"):
        allowed.append(f"matching {_code(pattern)}")
    return [label], allowed


def _text(value: object) -> str:
    """Render a JSON-mode value the way an environment variable carries it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _entry(group_type: type[MenageristBaseSettings], name: str) -> SettingEntry:
    field = group_type.model_fields[name]
    adapter: TypeAdapter[object] = field_adapter(field)
    try:
        schema = adapter.json_schema(by_alias=False)
    except PydanticInvalidForJsonSchema:
        schema = {}
    types, allowed = _describe(schema)
    sensitive = _is_sensitive(field, schema)
    raw = field.get_default(call_default_factory=True)
    value = adapter.dump_python(raw, mode="json")
    shown = mask_dsn(raw) if sensitive and "://" in str(raw) else None
    tunable = next((m for m in unwrap(field)[1] if isinstance(m, Tunable)), None)
    return SettingEntry(
        env_name=env_name(group_type, name),
        aliases=env_aliases(group_type, name),
        group=group_name(group_type),
        type_label=" or ".join(types) or "text",
        allowed=", ".join(allowed),
        description=field.description or "",
        default=None if sensitive or value is None else _text(value),
        shown_default=shown,
        sensitive=sensitive,
        tunable=tunable is not None,
        restart_required=tunable is not None and tunable.restart_required,
    )


def build_sections(
    groups: Iterable[type[MenageristBaseSettings]],
    compose_texts: Mapping[str, str] | None = None,
) -> list[SettingsSection]:
    """Describe every field of every class, merging classes that share a group.

    Fields marked `Internal` are left out. With `compose_texts` (the Compose files by
    name) the Compose variables follow as a last section.
    """
    entries: dict[str, list[SettingEntry]] = {}
    summaries: dict[str, str] = {}
    for group_type in groups:
        group = group_name(group_type)
        summary = (group_type.__doc__ or "").strip().splitlines()[0]
        summaries.setdefault(group, summary)
        entries.setdefault(group, []).extend(
            _entry(group_type, name)
            for name, field in group_type.model_fields.items()
            if not any(isinstance(m, Internal) for m in unwrap(field)[1])
        )
    sections = [
        SettingsSection(group=group, summary=summaries[group], entries=tuple(items))
        for group, items in entries.items()
        if items
    ]
    if compose_texts is not None:
        sections.append(_compose_section(compose_texts))
    return sections


def _compose_section(texts: Mapping[str, str]) -> SettingsSection:
    """Describe the Compose variables found in the Compose files."""
    variables = compose_defaults(texts)
    check_descriptions(variables)
    return SettingsSection(
        group=COMPOSE_GROUP,
        summary=COMPOSE_SUMMARY,
        entries=tuple(
            SettingEntry(
                env_name=name,
                aliases=(),
                group=COMPOSE_GROUP,
                type_label="text",
                allowed="",
                description=DESCRIPTIONS[name],
                default=default,
                shown_default=None,
                sensitive=False,
                tunable=False,
                restart_required=False,
            )
            for name, default in variables.items()
        ),
    )


def _dotenv_value(value: str) -> str:
    return f'"{value}"' if _UNSAFE_IN_DOTENV.search(value) else value


def _comment(text: str) -> list[str]:
    return [f"# {line}" for line in textwrap.wrap(text, _WIDTH - 2)]


def render_env_example(
    sections: Iterable[SettingsSection], *, enabled: bool = False
) -> str:
    """Render `.env.example`, every variable commented out with its default.

    Args:
        sections: The described settings.
        enabled: Uncomment each variable that has a default to write. Used to prove the
            defaults load; sensitive and unset variables stay commented.
    """
    lines = [
        "# Menagerist settings. Generated by `menagerist settings docs`; do not edit.",
        "# Copy to .env next to compose.yaml and uncomment only what you change.",
        f"# Every variable is described in {SETTINGS_DOC_PATH}.",
        *_comment(_IMAGE_NOTE.replace("`", "")),
    ]
    for section in sections:
        title = group_title(section.group)
        lines += [
            "",
            f"# {'=' * 4} {title} {'=' * (_WIDTH - 8 - len(title))}",
        ]
        lines += _comment(section.summary)
        for entry in section.entries:
            lines.append("")
            lines += _comment(entry.description)
            if entry.allowed:
                lines += _comment(f"Allowed: {entry.allowed}.")
            if entry.aliases:
                lines += _comment(f"Also read from {', '.join(entry.aliases)}.")
            if entry.sensitive:
                lines += _comment("Sensitive: no default is written here.")
            if entry.default is None:
                lines.append(f"# {entry.env_name}=")
                continue
            prefix = "" if enabled else "# "
            lines.append(f"{prefix}{entry.env_name}={_dotenv_value(entry.default)}")
    return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _default_cell(entry: SettingEntry) -> str:
    if entry.sensitive:
        return f"`{entry.shown_default}`" if entry.shown_default else "none (sensitive)"
    if entry.default is None:
        return "unset"
    return f"`{entry.default}`" if entry.default else "empty"


def _notes(entry: SettingEntry) -> str:
    notes = [entry.description]
    if entry.aliases:
        notes.append(f"Also read from `{'`, `'.join(entry.aliases)}`.")
    if entry.tunable:
        suffix = " Needs a restart." if entry.restart_required else ""
        notes.append(f"Editable in the app's settings unless set here.{suffix}")
    return " ".join(notes)


def render_settings_doc(sections: Iterable[SettingsSection]) -> str:
    """Render the settings reference: one table per group."""
    lines = [
        "# Settings reference",
        "",
        "<!-- Generated by `menagerist settings docs`; do not edit. -->",
        "",
        _INTRO,
        "",
        _IMAGE_NOTE,
    ]
    for section in sections:
        lines += ["", f"## {group_title(section.group)}", "", section.summary, ""]
        lines += [
            "| Variable | Type | Default | Allowed values | Notes |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            "| "
            + " | ".join(
                (
                    f"`{entry.env_name}`",
                    _cell(entry.type_label),
                    _cell(_default_cell(entry)),
                    _cell(entry.allowed or "any"),
                    _cell(_notes(entry)),
                )
            )
            + " |"
            for entry in section.entries
        ]
    return "\n".join(lines) + "\n"


def reference_files(
    groups: Iterable[type[MenageristBaseSettings]],
    compose_texts: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The generated files, as repository-relative paths and their contents."""
    sections = build_sections(groups, compose_texts)
    return {
        ENV_EXAMPLE_PATH: render_env_example(sections),
        SETTINGS_DOC_PATH: render_settings_doc(sections),
    }
