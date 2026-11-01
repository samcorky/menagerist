import json
from typing import Any

import jsonschema

from app.modules.graph.application.schema_meta import validation_schema
from app.modules.graph.domain.errors import InvalidAttributesError


def _canonical(value: object) -> str:
    """Return a type-strict canonical form, so `1`, `1.0` and `True` all differ."""
    return json.dumps(value, sort_keys=True)


def _is_unchanged(
    error: jsonschema.ValidationError,
    attributes: dict[str, Any],
    previous: dict[str, Any],
) -> bool:
    """Whether `error` sits under a top-level key whose value did not change."""
    if not error.absolute_path:
        return False
    key = str(error.absolute_path[0])
    return _canonical(attributes.get(key)) == _canonical(previous.get(key))


def validate_attributes(
    schema: dict[str, Any],
    attributes: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
) -> None:
    """Validate attributes against a JSON Schema.

    The root `required` array and archived properties are stripped first: the
    former is advisory only, the latter are hidden from forms.
    Uses iter_errors so all violations are collected in one pass.
    Each error carries a JSON Pointer path (e.g. "/year", "/prices/0/amount"),
    the failing keyword and its constraint value, so clients can word it.

    When `previous` is given (an update), errors under a top-level key whose
    value is unchanged are ignored, so a stale value never blocks an unrelated
    edit. Errors with no key (against the whole object) are always kept.

    :raises InvalidAttributesError with per-field paths.
    """
    effective = validation_schema(schema)
    _cls = jsonschema.validators.validator_for(effective)
    validator = _cls(effective, format_checker=_cls.FORMAT_CHECKER)
    errors = [
        {
            "path": "/" + "/".join(str(p) for p in err.absolute_path),
            "message": err.message,
            "keyword": str(err.validator),
            "value": err.validator_value,
        }
        for err in validator.iter_errors(attributes)
        if previous is None or not _is_unchanged(err, attributes, previous)
    ]
    if errors:
        raise InvalidAttributesError(errors)
