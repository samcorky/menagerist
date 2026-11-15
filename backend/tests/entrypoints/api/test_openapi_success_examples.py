"""Success responses carry the example of the model they return."""

import json
from pathlib import Path
from typing import Any

from app.entrypoints.api.openapi_examples import add_success_examples

# The committed API contract; CI keeps it identical to what the app generates.
SPEC = Path(__file__).parents[4] / "openapi.json"

_THING = {"id": "1", "name": "Alien"}


def _spec(responses: dict[str, Any]) -> dict[str, Any]:
    return {
        "paths": {"/things": {"get": {"responses": responses}}},
        "components": {"schemas": {"Thing": {"examples": [_THING, {"id": "2"}]}}},
    }


def _content(spec: dict[str, Any], status: str) -> dict[str, Any]:
    content = spec["paths"]["/things"]["get"]["responses"][status]["content"]
    return dict(content["application/json"])


def test_a_single_model_gets_its_first_example() -> None:
    """A `$ref` body takes the model's first example."""
    ref = {"$ref": "#/components/schemas/Thing"}
    spec = _spec({"200": {"content": {"application/json": {"schema": ref}}}})

    add_success_examples(spec)

    assert _content(spec, "200")["example"] == _THING


def test_a_list_gets_a_list_of_one_and_a_description() -> None:
    """An inline array of a model gets `[example]` and names its items."""
    schema = {"type": "array", "items": {"$ref": "#/components/schemas/Thing"}}
    spec = _spec({"200": {"content": {"application/json": {"schema": schema}}}})

    add_success_examples(spec)

    content = _content(spec, "200")
    assert content["example"] == [_THING]
    assert content["schema"]["description"] == "Each entry is a `Thing`."


def test_an_own_example_and_error_responses_are_left_alone() -> None:
    """A route's own example wins, and only 2xx responses are filled."""
    ref = {"$ref": "#/components/schemas/Thing"}
    spec = _spec(
        {
            "200": {"content": {"application/json": {"schema": ref, "example": {}}}},
            "404": {"content": {"application/json": {"schema": ref}}},
        }
    )

    add_success_examples(spec)

    assert _content(spec, "200")["example"] == {}
    assert "example" not in _content(spec, "404")


def test_every_json_success_body_in_the_contract_has_an_example() -> None:
    """The committed contract has no JSON success body without an example."""
    paths = json.loads(SPEC.read_text())["paths"]
    missing = [
        f"{method.upper()} {path} {status}"
        for path, item in paths.items()
        for method, operation in item.items()
        for status, response in operation["responses"].items()
        if status.startswith("2")
        for media_type, media in response.get("content", {}).items()
        if media_type.endswith("json")
        and "example" not in media
        and "examples" not in media
    ]

    assert missing == []
