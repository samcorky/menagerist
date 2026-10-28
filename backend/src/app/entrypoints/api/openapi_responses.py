"""Document the error statuses every `/api/v1` operation can emit.

Routes document only what is specific to them. The statuses the app adds
everywhere (authentication, permission, CSRF, missing resources, unhandled
errors) are attached here, and only where the operation has not already
documented that status itself. Each operation gets its own copy, so its
examples cite its own URL as the `instance`, not one shared route.
"""

import copy
import re
from typing import Any

from app.entrypoints.api.shared.http.problem_response import (
    INSTANCE_PLACEHOLDER,
    PROBLEM_JSON,
    ProblemDetail,
    problem_example,
)

_API_PREFIX = "/api/v1"
_UNSAFE_METHODS = frozenset({"post", "put", "patch", "delete"})
_METHODS = frozenset({"get", "put", "post", "delete", "patch"})
_PROBLEM_REF = {"$ref": "#/components/schemas/ProblemDetail"}
_ORIGIN = "https://menagerist.example"
_EXAMPLE_ID = "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10"
# Operations whose missing parent is answered with an empty result, not a 404.
_NO_NOT_FOUND = frozenset({"list_node_media"})

_UNPROCESSABLE = {
    "description": "A field is missing or has the wrong type.",
    "content": {
        PROBLEM_JSON: {
            "schema": {"$ref": "#/components/schemas/ValidationProblem"},
            "example": {
                "type": "about:blank",
                "title": "Unprocessable Content",
                "status": 422,
                "detail": [
                    {
                        "type": "missing",
                        "loc": ["body", "name"],
                        "msg": "Field required",
                    }
                ],
                "instance": INSTANCE_PLACEHOLDER,
            },
        }
    },
}


def _validation_problem_schema() -> dict[str, Any]:
    """Schema of the 422 body: `detail` lists the offending fields, not text."""
    return {
        "type": "object",
        "title": "ValidationProblem",
        "required": ["type", "title", "status", "detail", "instance"],
        "properties": {
            "type": {"type": "string"},
            "title": {"type": "string"},
            "status": {"type": "integer"},
            "detail": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["type", "loc", "msg"],
                    "properties": {
                        "type": {"type": "string"},
                        "loc": {
                            "type": "array",
                            "items": {
                                "anyOf": [{"type": "string"}, {"type": "integer"}]
                            },
                        },
                        "msg": {"type": "string"},
                    },
                },
            },
            "instance": {"type": "string"},
        },
    }


def _problem(
    description: str, examples: dict[str, tuple[str, dict[str, Any]]]
) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            PROBLEM_JSON: {
                "schema": _PROBLEM_REF,
                "examples": {
                    key: {"summary": summary, "value": value}
                    for key, (summary, value) in examples.items()
                },
            }
        },
    }


_NOT_SIGNED_IN = (
    "Not signed in",
    problem_example(
        401,
        "SessionRequiredError",
        "Sign in to continue.",
        type_="unauthenticated",
    ),
)
_SETUP_REQUIRED = (
    "No account exists yet",
    problem_example(
        401,
        "SetupRequiredError",
        "Create the first account to continue.",
        type_="setup_required",
    ),
)
_INVALID_TOKEN = (
    "Bearer token not valid",
    problem_example(
        401,
        "InvalidApiTokenError",
        "The access token is not valid.",
        type_="invalid_token",
    ),
)
_REFUSED = (
    "Permission refused",
    problem_example(403, "ForbiddenError", "You do not have permission to do that."),
)
_PASSWORD_EXPIRED = (
    "Password must be changed",
    problem_example(
        403,
        "PasswordExpiredError",
        "Change your password to continue.",
        type_="password_expired",
    ),
)
_CSRF_FAILED = (
    "Request not from this site",
    problem_example(
        403,
        "CsrfError",
        "This request was not sent from this site's own pages.",
        type_="csrf_failed",
    ),
)

_SIGNED_OUT = "Not signed in, or the session is no longer valid."
_TOKEN_NOTE = (
    " A bearer token that is unknown, expired, revoked or whose owner is disabled"
    + " is refused with problem type `invalid_token`."
)
_FORBIDDEN = (
    "Not permitted: the account or token lacks the permission, or the password"
    + " must be changed first (`password_expired`)."
)
_CSRF_NOTE = (
    " A cookie-authenticated request that did not come from this site's own"
    + " pages is refused with `csrf_failed`."
)

_RESPONSES: dict[str, dict[str, Any]] = {
    "Unauthenticated": _problem(
        _SIGNED_OUT,
        {"not_signed_in": _NOT_SIGNED_IN, "setup_required": _SETUP_REQUIRED},
    ),
    "UnauthenticatedToken": _problem(
        _SIGNED_OUT + _TOKEN_NOTE,
        {
            "not_signed_in": _NOT_SIGNED_IN,
            "setup_required": _SETUP_REQUIRED,
            "invalid_token": _INVALID_TOKEN,
        },
    ),
    "Forbidden": _problem(
        _FORBIDDEN,
        {"permission_refused": _REFUSED, "password_expired": _PASSWORD_EXPIRED},
    ),
    "ForbiddenUnsafe": _problem(
        _FORBIDDEN + _CSRF_NOTE,
        {
            "permission_refused": _REFUSED,
            "csrf_failed": _CSRF_FAILED,
            "password_expired": _PASSWORD_EXPIRED,
        },
    ),
    "NotFound": _problem(
        "Not found, or not yours: someone else's resource is reported as missing.",
        {
            "not_found": (
                "Resource not found",
                problem_example(404, "NotFoundError", "The resource was not found."),
            )
        },
    ),
    "InternalError": _problem(
        "Unexpected server error. The detail is generic; the cause is only logged.",
        {
            "internal_error": (
                "Unhandled error",
                problem_example(
                    500, "Internal Server Error", "An unexpected error occurred."
                ),
            )
        },
    ),
}


def _add_missing(operation: dict[str, Any], status: int, name: str) -> None:
    operation["responses"].setdefault(str(status), copy.deepcopy(_RESPONSES[name]))


def _example_path(path: str, operation: dict[str, Any]) -> str:
    """Fill a route pattern's parameters with example values."""
    schemas = {
        parameter["name"]: parameter.get("schema", {})
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "path"
    }

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        return _EXAMPLE_ID if schemas.get(name, {}).get("format") == "uuid" else name

    return re.sub(r"\{([^}]+)\}", fill, path)


def _fill_instance(response: dict[str, Any], status: str, path: str) -> None:
    """Replace the placeholder `instance` in a response's problem+json examples."""
    content = response.get("content", {}).get(PROBLEM_JSON)
    if content is None:
        return
    # The upload limit answers with the bare path; handlers answer with the URL.
    instance = path if status == "413" else f"{_ORIGIN}{path}"
    bodies = [content.get("example")] + [
        entry.get("value") for entry in content.get("examples", {}).values()
    ]
    for body in bodies:
        if isinstance(body, dict) and body.get("instance") == INSTANCE_PLACEHOLDER:
            body["instance"] = instance


def _document_operation(path: str, method: str, operation: dict[str, Any]) -> None:
    security = operation.get("security") or []
    if security:
        bearer = any("HTTPBearer" in requirement for requirement in security)
        _add_missing(
            operation, 401, "UnauthenticatedToken" if bearer else "Unauthenticated"
        )
        unsafe = method in _UNSAFE_METHODS
        _add_missing(operation, 403, "ForbiddenUnsafe" if unsafe else "Forbidden")
    if "{" in path and operation.get("operationId") not in _NO_NOT_FOUND:
        _add_missing(operation, 404, "NotFound")
    _add_missing(operation, 500, "InternalError")
    if "422" in operation["responses"]:
        operation["responses"]["422"] = copy.deepcopy(_UNPROCESSABLE)
    example_path = _example_path(path, operation)
    for status, response in operation["responses"].items():
        _fill_instance(response, status, example_path)
    operation["responses"] = dict(sorted(operation["responses"].items()))


def add_error_responses(openapi_schema: dict[str, Any]) -> None:
    """Attach the common error responses to every `/api/v1` operation, keeping its own.

    Also gives every problem+json example an `instance` that fits its route and
    replaces FastAPI's 422 entry with the problem+json body the app really sends.
    """
    components = openapi_schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    schemas.setdefault("ProblemDetail", ProblemDetail.model_json_schema())
    schemas["ValidationProblem"] = _validation_problem_schema()
    for path, item in openapi_schema.get("paths", {}).items():
        if not path.startswith(_API_PREFIX):
            continue
        for method, operation in item.items():
            if method not in _METHODS:
                continue
            _document_operation(path, method, operation)
