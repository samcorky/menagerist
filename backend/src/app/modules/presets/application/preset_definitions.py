"""Structural checks for a preset's `definition`, one shape per `kind`.

These check the definition is well-formed enough to apply later (WI-19b/c); they
do not validate a `field`'s property as full JSON Schema - the schema-owning
module (`graph`) does that when the copy is actually inserted into a schema.
"""

from typing import Any

from app.modules.presets.domain.errors import InvalidPresetDefinitionError


def _check_field(definition: dict[str, Any]) -> None:
    prop = definition.get("property")
    if not isinstance(prop, dict) or not prop:
        raise InvalidPresetDefinitionError(
            "a field preset needs a non-empty 'property' object"
        )
    if "type" not in prop:
        raise InvalidPresetDefinitionError("'property' must have a 'type'")


def _check_field_set(definition: dict[str, Any]) -> None:
    section = definition.get("section")
    if not isinstance(section, str) or section.strip() == "":
        raise InvalidPresetDefinitionError(
            "a field group preset needs a non-empty 'section' label"
        )
    properties = definition.get("properties")
    if not isinstance(properties, list) or not properties:
        raise InvalidPresetDefinitionError(
            "a field group preset needs a non-empty 'properties' array"
        )
    if not all(isinstance(p, dict) and "type" in p for p in properties):
        raise InvalidPresetDefinitionError("each property must have a 'type'")


def _check_choice_list(definition: dict[str, Any]) -> None:
    options = definition.get("options")
    if not isinstance(options, list) or not options:
        raise InvalidPresetDefinitionError(
            "a list preset needs a non-empty 'options' array"
        )
    if not all(isinstance(o, str) and o.strip() for o in options):
        raise InvalidPresetDefinitionError("every option must be a non-blank string")


_CHECKS = {
    "field": _check_field,
    "field_set": _check_field_set,
    "choice_list": _check_choice_list,
}


def check_definition(kind: str, definition: dict[str, Any]) -> None:
    """Check `definition`'s shape for `kind`.

    :raises InvalidPresetDefinitionError: when the kind is unknown or malformed.
    """
    check = _CHECKS.get(kind)
    if check is None:
        raise InvalidPresetDefinitionError(f"unknown preset kind '{kind}'")
    check(definition)
