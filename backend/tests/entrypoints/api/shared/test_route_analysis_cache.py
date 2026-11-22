from typing import TYPE_CHECKING, Annotated, Any, cast

import pytest
from fastapi import Depends, FastAPI, Security
from fastapi._compat import v2
from fastapi.dependencies import utils
from fastapi.testclient import TestClient
from fastapi.utils import create_model_field
from pydantic import ConfigDict, ValidationError
from pydantic.fields import FieldInfo

from app.entrypoints.api.shared import route_analysis_cache

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.dependencies.models import Dependant
    from pydantic import TypeAdapter

route_analysis_cache.install()

# FastAPI does not export `TypeAdapter` from this module; it is the name its fields
# look up, which is what the cache replaces.
fields: Any = v2


def _dependency(value: int = 1) -> int:
    return value


class _Unhashable:
    __hash__ = None  # type: ignore[assignment]

    def __call__(self, value: int = 1) -> int:
        return value


def _route(value: Annotated[int, Depends(_dependency)]) -> int:
    return value


def _sub_dependant(path: str, route: Callable[..., object] = _route) -> Dependant:
    return utils.get_dependant(path=path, call=route).dependencies[0]


def _adapter(
    name: str = "x", constraints: dict[str, object] | None = None
) -> TypeAdapter[Any]:
    field_info = FieldInfo(annotation=int, **cast(dict[str, Any], constraints or {}))
    return create_model_field(name=name, type_=int, field_info=field_info)._type_adapter


def test_repeated_analysis_of_one_callable_returns_the_same_signature() -> None:
    """A shared dependency is analysed once, however many routes use it."""
    first = utils.get_typed_signature(_dependency)

    assert utils.get_typed_signature(_dependency) is first


def test_install_is_idempotent() -> None:
    """Installing twice does not wrap the caches in a second layer."""
    installed = (utils.get_typed_signature, utils.get_dependant, fields.TypeAdapter)

    route_analysis_cache.install()

    assert (
        utils.get_typed_signature,
        utils.get_dependant,
        fields.TypeAdapter,
    ) == installed


def test_unhashable_callable_is_analysed_without_caching() -> None:
    """A callable that cannot be a cache key still gets its signature."""
    dependency: Any = _Unhashable()

    signature = utils.get_typed_signature(dependency)

    assert list(signature.parameters) == ["value"]
    assert utils.get_typed_signature(dependency) is not signature


def test_a_shared_dependency_is_built_once_for_one_path_shape() -> None:
    """Routes with the same path parameters share their sub-dependency's tree."""
    assert _sub_dependant("/items/{item_id}") is _sub_dependant("/things/{item_id}")


def test_a_dependency_is_built_again_for_different_path_parameters() -> None:
    """A path parameter changes how a dependency reads its own parameters."""

    def by_id(item_id: int) -> int:
        return item_id

    def route(value: Annotated[int, Depends(by_id)]) -> int:
        return value

    on_path = _sub_dependant("/items/{item_id}", route)
    off_path = _sub_dependant("/items", route)

    assert on_path is not off_path
    assert [f.name for f in on_path.path_params] == ["item_id"]
    assert [f.name for f in off_path.query_params] == ["item_id"]


def test_a_route_keeps_its_own_dependant() -> None:
    """Callers add to a route's dependant, so it is never shared."""
    first = utils.get_dependant(path="/items", call=_route)
    second = utils.get_dependant(path="/items", call=_route)

    first.dependencies.clear()

    assert first is not second
    assert len(second.dependencies) == 1


def test_oauth_scopes_are_part_of_the_dependency_key() -> None:
    """The same dependency under different scopes is not shared."""

    def reading(value: Annotated[int, Security(_dependency, scopes=["read"])]) -> int:
        return value

    def writing(value: Annotated[int, Security(_dependency, scopes=["write"])]) -> int:
        return value

    assert _sub_dependant("/a", reading).own_oauth_scopes == ["read"]
    assert _sub_dependant("/a", writing).own_oauth_scopes == ["write"]


def test_an_unhashable_dependency_is_built_without_sharing() -> None:
    """A dependency that cannot be a cache key still gets a dependency tree."""
    dependency: Any = _Unhashable()

    def route(value: Annotated[int, Depends(dependency)]) -> int:
        return value

    first = _sub_dependant("/a", route)

    assert first.call is dependency
    assert _sub_dependant("/a", route) is not first


def test_an_overridden_shared_dependency_still_reads_its_own_parameters() -> None:
    """Dependency overrides rebuild the tree from the shared sub-dependency's path."""

    def by_id(item_id: int) -> int:
        return item_id

    def times_ten(item_id: int) -> int:
        return item_id * 10

    app = FastAPI()

    @app.get("/items/{item_id}")
    def on_path(value: Annotated[int, Depends(by_id)]) -> int:
        return value

    @app.get("/other")
    def in_query(value: Annotated[int, Depends(by_id)]) -> int:
        return value

    app.dependency_overrides[by_id] = times_ten
    client = TestClient(app)

    assert client.get("/items/3").json() == 30
    assert client.get("/other", params={"item_id": 4}).json() == 40


def test_fields_of_one_shape_share_an_adapter_whatever_their_names() -> None:
    """The adapter depends on the type and constraints, not on the field's name."""
    assert _adapter("a", {"ge": 1}) is _adapter("b", {"ge": 1})


def test_fields_with_different_constraints_do_not_share_an_adapter() -> None:
    """Each constraint is still enforced by its own adapter."""
    at_least_one = _adapter(constraints={"ge": 1})
    at_least_two = _adapter(constraints={"ge": 2})

    assert at_least_one is not at_least_two
    assert at_least_one.validate_python(1) == 1
    with pytest.raises(ValidationError):
        at_least_two.validate_python(1)


def test_equal_but_differently_written_constraints_do_not_share_an_adapter() -> None:
    """`0` and `0.0` compare equal but are not the same constraint."""
    assert _adapter(constraints={"gt": 0}) is not _adapter(constraints={"gt": 0.0})


def test_unhashable_field_attributes_get_their_own_adapter() -> None:
    """A field that cannot be a cache key is still built."""
    first = _adapter(constraints={"json_schema_extra": {"x": 1}})
    second = _adapter(constraints={"json_schema_extra": {"x": 1}})

    assert first is not second
    assert first.validate_python(1) == 1


def test_an_adapter_with_its_own_config_or_plain_type_is_not_shared() -> None:
    """Only the shape FastAPI builds for its fields is shared."""
    strict = ConfigDict(strict=True)

    assert fields.TypeAdapter(int) is not fields.TypeAdapter(int)
    annotated = Annotated[int, FieldInfo()]
    assert fields.TypeAdapter(annotated, config=strict) is not fields.TypeAdapter(
        annotated, config=strict
    )


def test_install_refuses_a_get_dependant_it_does_not_understand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A changed FastAPI fails start-up instead of quietly caching wrongly."""

    def changed(*, route: str) -> object:
        return route

    monkeypatch.setattr(utils, "get_dependant", changed)

    with pytest.raises(RuntimeError, match="get_dependant no longer takes"):
        route_analysis_cache._share_sub_dependants()


def test_install_refuses_fields_that_no_longer_use_type_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A changed FastAPI fails start-up instead of quietly caching nothing."""
    monkeypatch.setattr(v2, "TypeAdapter", object)

    with pytest.raises(RuntimeError, match="TypeAdapter"):
        route_analysis_cache._share_type_adapters()
