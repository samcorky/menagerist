"""Do FastAPI's route-construction work once where routes share it.

FastAPI analyses every route from scratch. The same dependencies sit under almost
every route (the session factory, the access guard), and most routes take the same
few parameter types, so on a small device building the routes was the larger part of
the start-up import. Three caches remove the repeats without changing what is built:

- a callable's signature is analysed once;
- a shared sub-dependency's `Dependant` is built once per path shape;
- the Pydantic `TypeAdapter` behind a parameter is built once per distinct field.

All three patch FastAPI internals. Each checks what it relies on and raises at
start-up if FastAPI has changed, rather than quietly doing nothing.
"""

import functools
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated, Any, cast, get_args, get_origin

from fastapi._compat import v2
from fastapi.dependencies import utils
from fastapi.utils import get_path_param_names
from pydantic import ConfigDict, TypeAdapter
from pydantic.fields import FieldInfo

if TYPE_CHECKING:
    from fastapi.dependencies.models import Dependant

_Signature = Callable[..., inspect.Signature]


def _require(condition: bool, what: str) -> None:
    if not condition:
        raise RuntimeError(
            f"Cannot speed up route construction: {what}. FastAPI's internals have "
            + "changed; update app.entrypoints.api.shared.route_analysis_cache."
        )


def _exact(value: object) -> tuple[object, str]:
    """Key a value by equality and repr, so `0` and `0.0` are different keys."""
    return value, repr(value)


def _share_signatures() -> None:
    original: _Signature = utils.get_typed_signature
    cached = functools.cache(original)

    @functools.wraps(original)
    def get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
        try:
            return cached(call)
        except TypeError:
            # An unhashable callable (an instance with `__call__` and `__eq__`).
            return original(call)

    utils.get_typed_signature = get_typed_signature


def _share_sub_dependants() -> None:
    """Build each sub-dependency's `Dependant` once per path shape.

    A route's own `Dependant` is always built fresh, since callers add to it. A
    sub-dependency's tree depends on the path only through its parameter names, which
    is what the key holds. Its `path` attribute is the first route's, and FastAPI
    reads that only to rebuild the tree for an overridden dependency, again for the
    names.
    """
    original = cast(Callable[..., "Dependant"], utils.get_dependant)
    names = inspect.signature(original).parameters.keys()
    _require(
        {"path", "call", "name"} <= names,
        "get_dependant no longer takes path, call and name",
    )
    shared: dict[object, Dependant] = {}

    @functools.wraps(original)
    def get_dependant(**kwargs: object) -> Dependant:
        if kwargs.get("name") is None:
            return original(**kwargs)
        try:
            key = (
                frozenset(get_path_param_names(str(kwargs["path"]))),
                tuple(
                    sorted(
                        (name, tuple(v) if isinstance(v, list) else v)
                        for name, v in kwargs.items()
                        if name != "path"
                    )
                ),
            )
            hash(key)
        except TypeError:
            return original(**kwargs)
        if key not in shared:
            shared[key] = original(**kwargs)
        return shared[key]

    utils.get_dependant = get_dependant


def _adapter_key(type_: object) -> object | None:
    """Return what makes two field adapters interchangeable, or None if unknown.

    FastAPI builds the adapter from the annotation, its constraints and a trailing
    `FieldInfo` holding the remaining attributes. The field's name is not part of it.
    """
    if get_origin(type_) is not Annotated:
        return None
    annotation, *metadata = get_args(type_)
    if not metadata or not isinstance(metadata[-1], FieldInfo):
        return None
    attributes = metadata[-1].asdict()["attributes"]
    try:
        key = (
            annotation,
            tuple(_exact(m) for m in metadata[:-1]),
            tuple((name, _exact(v)) for name, v in attributes.items()),
        )
        hash(key)
    except TypeError:
        return None
    return key


def _share_type_adapters() -> None:
    _require(
        getattr(v2, "TypeAdapter", None) is TypeAdapter,
        "fastapi._compat.v2 no longer builds its fields with pydantic.TypeAdapter",
    )
    shared: dict[object, TypeAdapter[Any]] = {}

    def type_adapter(
        type_: object, *, config: ConfigDict | None = None
    ) -> TypeAdapter[Any]:
        key = _adapter_key(type_) if config is None else None
        if key is None:
            return TypeAdapter(cast(Any, type_), config=config)
        if key not in shared:
            shared[key] = TypeAdapter(cast(Any, type_))
        return shared[key]

    cast(Any, v2).TypeAdapter = type_adapter


@functools.cache
def install() -> None:
    """Share the work between routes. Idempotent.

    Must run before any router module is imported.
    """
    _share_signatures()
    _share_sub_dependants()
    _share_type_adapters()
