"""Every `/api/v1` operation documents the error statuses the app can emit."""

from typing import Any

import pytest

from app.entrypoints.api import create_app

_METHODS = ("get", "put", "post", "delete", "patch")
_UNSAFE = ("put", "post", "delete", "patch")
# Answer an unknown parent with an empty list, never a 404.
_NO_NOT_FOUND = {"list_node_media"}


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """The generated OpenAPI document."""
    return create_app().openapi()


def _operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method, path, operation)
        for path, item in schema["paths"].items()
        if path.startswith("/api/v1")
        for method, operation in item.items()
        if method in _METHODS
    ]


def test_secured_operations_document_401_and_403(schema: dict[str, Any]) -> None:
    """Secured operations document 401 and 403."""
    missing = [
        f"{m.upper()} {p}"
        for m, p, o in _operations(schema)
        if o.get("security") and not {"401", "403"} <= set(o["responses"])
    ]
    assert missing == []


def test_unsafe_operations_with_security_document_403(schema: dict[str, Any]) -> None:
    """Unsafe operations with security document 403."""
    missing = [
        f"{m.upper()} {p}"
        for m, p, o in _operations(schema)
        if m in _UNSAFE and o.get("security") and "403" not in o["responses"]
    ]
    assert missing == []


def test_path_parameter_operations_document_404(schema: dict[str, Any]) -> None:
    """Path parameter operations document 404."""
    missing = [
        f"{m.upper()} {p}"
        for m, p, o in _operations(schema)
        if "{" in p
        and "404" not in o["responses"]
        and o["operationId"] not in _NO_NOT_FOUND
    ]
    assert missing == []


def test_every_operation_documents_500(schema: dict[str, Any]) -> None:
    """Every operation documents 500."""
    missing = [
        f"{m.upper()} {p}"
        for m, p, o in _operations(schema)
        if "500" not in o["responses"]
    ]
    assert missing == []


def test_health_probes_are_left_alone(schema: dict[str, Any]) -> None:
    """Health probes are left alone."""
    assert set(schema["paths"]["/api/health"]["get"]["responses"]) == {"200"}
    assert set(schema["paths"]["/api/health/ready"]["get"]["responses"]) == {
        "200",
        "503",
    }


def test_public_operations_get_no_invented_auth_statuses(
    schema: dict[str, Any],
) -> None:
    """Public operations get no invented auth statuses."""
    status = schema["paths"]["/api/v1/auth/status"]["get"]["responses"]
    assert set(status) == {"200", "500"}


def _collect_refs(node: object) -> set[str]:
    if isinstance(node, dict):
        found = {node["$ref"]} if isinstance(node.get("$ref"), str) else set()
        return found.union(*(_collect_refs(v) for v in node.values()))
    if isinstance(node, list):
        return set().union(*(_collect_refs(v) for v in node))
    return set()


def test_no_reference_dangles(schema: dict[str, Any]) -> None:
    """No reference dangles."""
    for ref in _collect_refs(schema):
        target: Any = schema
        for part in ref.removeprefix("#/").split("/"):
            assert part in target, ref
            target = target[part]


def test_shared_responses_use_problem_json_schema(schema: dict[str, Any]) -> None:
    """Shared responses use problem json schema."""
    for response in schema["components"]["responses"].values():
        content = response["content"]["application/problem+json"]
        assert content["schema"] == {"$ref": "#/components/schemas/ProblemDetail"}


def test_route_specific_entries_are_not_overwritten(schema: dict[str, Any]) -> None:
    """Route specific entries are not overwritten."""
    login = schema["paths"]["/api/v1/auth/login"]["post"]["responses"]
    for code in ("401", "403", "429"):
        assert "$ref" not in login[code]
    assert "another site" in login["403"]["description"]
    revoke = schema["paths"]["/api/v1/auth/sessions/{session_id}"]["delete"][
        "responses"
    ]
    assert "$ref" not in revoke["401"]
    assert "$ref" not in revoke["404"]
    patch = schema["paths"]["/api/v1/node/{node_id}"]["patch"]["responses"]
    assert patch["412"]["description"].startswith("Precondition failed")


def test_bearer_operations_mention_invalid_token(schema: dict[str, Any]) -> None:
    """Bearer operations mention invalid token."""
    node = schema["paths"]["/api/v1/node"]["post"]["responses"]
    assert node["401"] == {"$ref": "#/components/responses/UnauthenticatedToken"}
    assert node["403"] == {"$ref": "#/components/responses/ForbiddenUnsafe"}
    cookie_only = schema["paths"]["/api/v1/backup"]["get"]["responses"]
    assert cookie_only["401"] == {"$ref": "#/components/responses/Unauthenticated"}
