from typing import Any

import jsonschema

from app.modules.graph.application.schema_meta import validation_schema
from app.modules.graph.domain.errors import InvalidAttributesError


def validate_attributes(schema: dict[str, Any], attributes: dict[str, Any]) -> None:
    """Validate attributes against a JSON Schema.

    The root `required` array and archived properties are stripped first: the
    former is advisory only, the latter are hidden from forms.
    Uses iter_errors so all violations are collected in one pass.
    Each error carries a JSON Pointer path (e.g. "/year", "/prices/0/amount").

    :raises InvalidAttributesError with per-field paths.
    """
    effective = validation_schema(schema)
    _cls = jsonschema.validators.validator_for(effective)
    validator = _cls(effective, format_checker=_cls.FORMAT_CHECKER)
    errors = [
        {
            "path": "/" + "/".join(str(p) for p in err.absolute_path),
            "message": err.message,
        }
        for err in validator.iter_errors(attributes)
    ]
    if errors:
        raise InvalidAttributesError(errors)
