import importlib
import pkgutil
from typing import Any

import jsonschema
import pytest
from pydantic import BaseModel

# Import the app first: routers have a circular import that resolves only in app order.
import app.entrypoints.api
import app.modules
from app.entrypoints.api import create_app
from app.platform.request_model import RequestModel

_COMPONENTS: dict[str, Any] = create_app().openapi()["components"]


def _api_models() -> list[type[BaseModel]]:
    """Every BaseModel defined in a module under `adapters/api` or `entrypoints/api`."""
    models: list[type[BaseModel]] = []
    for info in pkgutil.walk_packages(app.modules.__path__, "app.modules."):
        if ".adapters.api" in info.name:
            models.extend(_models_in(info.name))
    for info in pkgutil.walk_packages(
        app.entrypoints.api.__path__, "app.entrypoints.api."
    ):
        models.extend(_models_in(info.name))
    return models


def _models_in(module_name: str) -> list[type[BaseModel]]:
    module = importlib.import_module(module_name)
    return [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == module.__name__
    ]


def _examples(model: type[BaseModel]) -> list[dict[str, Any]]:
    extra = model.model_config.get("json_schema_extra")
    if not isinstance(extra, dict):
        return []
    examples = extra.get("examples", [])
    if not isinstance(examples, list):
        return []
    return [example for example in examples if isinstance(example, dict)]


def test_api_request_models_subclass_request_model() -> None:
    """Every `*Request` body model forbids unknown fields via `RequestModel`."""
    requests = [model for model in _api_models() if model.__name__.endswith("Request")]

    assert requests
    for model in requests:
        assert issubclass(model, RequestModel), model.__name__


@pytest.mark.parametrize("model", _api_models(), ids=lambda m: m.__name__)
def test_every_api_model_has_examples(model: type[BaseModel]) -> None:
    """Every API model documents at least one example."""
    assert _examples(model), f"{model.__name__} has no OpenAPI examples"


@pytest.mark.parametrize("model", _api_models(), ids=lambda m: m.__name__)
def test_openapi_examples_match_model(model: type[BaseModel]) -> None:
    """Each OpenAPI example uses only known fields and validates against its model."""
    known = set(model.model_fields) | {
        field.alias for field in model.model_fields.values() if field.alias
    }

    for example in _examples(model):
        unknown = set(example) - known
        assert not unknown, f"{model.__name__} example has unknown keys: {unknown}"
        model.model_validate(example)


_API_MODEL_NAMES = {model.__name__ for model in _api_models()}


@pytest.mark.parametrize(
    "name", [name for name in _COMPONENTS["schemas"] if name in _API_MODEL_NAMES]
)
def test_served_api_schemas_validate_their_examples(name: str) -> None:
    """Each served API schema validates its examples against its JSON Schema."""
    schema = _COMPONENTS["schemas"][name]
    assert schema.get("examples"), f"{name} is served without examples"
    # Resolve `$ref`s against the same components the app serves.
    root = {**schema, "components": _COMPONENTS}

    for example in schema["examples"]:
        jsonschema.validate(example, root)
