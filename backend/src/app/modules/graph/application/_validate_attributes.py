from typing import Any

import jsonschema

from app.modules.graph.domain.errors import InvalidAttributesError


def validate_attributes(schema: dict[str, Any], attributes: dict[str, Any]) -> None:
    """Validate attributes against a JSON Schema.

    Uses iter_errors so all violations are collected in one pass.
    Each error carries a JSON Pointer path (e.g. "/year", "/prices/0/amount").

    :raises InvalidAttributesError with per-field paths.
    """
    _cls = jsonschema.validators.validator_for(schema)
    validator = _cls(schema, format_checker=_cls.FORMAT_CHECKER)
    errors = [
        {
            "path": "/" + "/".join(str(p) for p in err.absolute_path),
            "message": err.message,
        }
        for err in validator.iter_errors(attributes)
    ]
    if errors:
        raise InvalidAttributesError(errors)
