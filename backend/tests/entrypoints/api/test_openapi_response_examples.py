"""Every documented response has an accurate description and example."""

import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit

import pytest
from pydantic import TypeAdapter

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.http.problem_response import (
    INSTANCE_PLACEHOLDER,
    ProblemDetail,
)

_METHODS = ("get", "put", "post", "delete", "patch")
_PROBLEM = "application/problem+json"
_REQUIRED = ("type", "title", "detail", "instance")


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """The generated OpenAPI document."""
    return create_app().openapi()


def _resolve(schema: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    ref = response.get("$ref")
    if ref is None:
        return response
    target: Any = schema
    for part in ref.removeprefix("#/").split("/"):
        target = target[part]
    assert isinstance(target, dict)
    return target


def _responses(
    schema: dict[str, Any],
) -> list[tuple[str, str, str, str, dict[str, Any]]]:
    """Return (label, path, method, status, resolved response) for each response."""
    return [
        (f"{m.upper()} {p} {code}", p, m, code, _resolve(schema, response))
        for p, item in schema["paths"].items()
        for m, operation in item.items()
        if m in _METHODS
        for code, response in operation["responses"].items()
    ]


def _problem_bodies(response: dict[str, Any]) -> list[dict[str, Any]]:
    content = response.get("content", {}).get(_PROBLEM)
    if content is None:
        return []
    bodies = [content["example"]] if "example" in content else []
    bodies += [entry["value"] for entry in content.get("examples", {}).values()]
    return bodies


def _route_pattern(path: str) -> re.Pattern[str]:
    return re.compile(re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")


def test_every_response_has_a_description(schema: dict[str, Any]) -> None:
    """Every response has a non-empty description."""
    bad = [
        label
        for label, *_rest, response in _responses(schema)
        if not str(response.get("description", "")).strip()
    ]
    assert bad == []


def _has_example(response: dict[str, Any]) -> bool:
    return any(
        "example" in media or "examples" in media
        for media in response.get("content", {}).values()
    )


def test_descriptions_are_not_raw_docstrings(schema: dict[str, Any]) -> None:
    """Descriptions speak of the response, not of a raised exception."""
    bad = [
        label
        for label, *_rest, response in _responses(schema)
        if str(response.get("description", "")).startswith("Raised")
    ]
    assert bad == []


def test_error_responses_have_body_examples(schema: dict[str, Any]) -> None:
    """Every 4xx and 5xx response has its own example (412 has no body).

    Swagger falls back to the schema example otherwise, whatever the status.
    """
    bad = [
        label
        for label, _p, _m, code, response in _responses(schema)
        if code.isdigit()
        and int(code) >= 400
        and code != "412"
        and not _has_example(response)
    ]
    assert bad == []


def test_problem_examples_match_their_status(schema: dict[str, Any]) -> None:
    """Each problem example is complete and its status equals the response code."""
    bad: list[str] = []
    for label, _p, _m, code, response in _responses(schema):
        for body in _problem_bodies(response):
            if body.get("status") != int(code) or any(k not in body for k in _REQUIRED):
                bad.append(label)
            if INSTANCE_PLACEHOLDER in str(body) or body.get("instance") == "string":
                bad.append(f"{label} placeholder")
    assert bad == []


def test_problem_example_instances_fit_their_route(schema: dict[str, Any]) -> None:
    """Route-level examples cite a URL whose path matches the route pattern."""
    bad: list[str] = []
    for p, item in schema["paths"].items():
        for m, operation in item.items():
            if m not in _METHODS:
                continue
            for code, response in operation["responses"].items():
                for body in _problem_bodies(response):
                    path = urlsplit(body["instance"]).path
                    if not _route_pattern(p).match(path):
                        bad.append(f"{m.upper()} {p} {code}: {body['instance']}")
    assert bad == []


def test_shared_responses_are_not_reused_across_statuses(
    schema: dict[str, Any],
) -> None:
    """A shared response is only referenced under its own status code."""
    statuses: dict[str, set[str]] = defaultdict(set)
    for item in schema["paths"].values():
        for m, operation in item.items():
            if m not in _METHODS:
                continue
            for code, response in operation["responses"].items():
                if "$ref" in response:
                    statuses[response["$ref"]].add(code)
    assert all(len(codes) == 1 for codes in statuses.values()), statuses
    for ref, codes in statuses.items():
        name = ref.rsplit("/", 1)[-1]
        shared = schema["components"]["responses"][name]
        assert {str(b["status"]) for b in _problem_bodies(shared)} == codes


def test_shared_401_and_403_name_each_problem_type(schema: dict[str, Any]) -> None:
    """The shared responses show one named example per problem type."""
    components = schema["components"]["responses"]

    def types(name: str) -> set[str]:
        return {b["type"] for b in _problem_bodies(components[name])}

    assert types("UnauthenticatedToken") == {
        "unauthenticated",
        "setup_required",
        "invalid_token",
    }
    assert types("Unauthenticated") == {"unauthenticated", "setup_required"}
    assert types("ForbiddenUnsafe") == {
        "about:blank",
        "csrf_failed",
        "password_expired",
    }
    assert types("Forbidden") == {"about:blank", "password_expired"}


def test_problem_examples_validate_against_problem_detail(
    schema: dict[str, Any],
) -> None:
    """Examples under the ProblemDetail schema validate as that model."""
    adapter = TypeAdapter(ProblemDetail)
    for _label, _p, _m, _code, response in _responses(schema):
        content = response.get("content", {}).get(_PROBLEM, {})
        if content.get("schema") != {"$ref": "#/components/schemas/ProblemDetail"}:
            continue
        for body in _problem_bodies(response):
            adapter.validate_python(body)


def test_validation_responses_describe_the_real_body(schema: dict[str, Any]) -> None:
    """422 is documented as problem+json, as the app sends it."""
    for label, _p, _m, code, response in _responses(schema):
        if code == "422":
            assert list(response["content"]) == [_PROBLEM], label
            assert _problem_bodies(response)[0]["title"] == "Unprocessable Content"


def test_error_response_types_match_the_exception_class(schema: dict[str, Any]) -> None:
    """Identity problem types appear where the app emits them."""
    login = schema["paths"]["/api/v1/auth/login"]["post"]["responses"]
    assert _problem_bodies(login["403"])[0]["type"] == "account_disabled"
    token = schema["paths"]["/api/v1/node"]["post"]["responses"]["401"]
    assert "$ref" in token


def test_references_to_shared_responses_resolve(schema: dict[str, Any]) -> None:
    """Every response reference resolves to a component."""
    for item in schema["paths"].values():
        for m, operation in item.items():
            if m not in _METHODS:
                continue
            for response in operation["responses"].values():
                if "$ref" in response:
                    assert _resolve(schema, response)["description"]
