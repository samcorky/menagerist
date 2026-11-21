import functools
import inspect
from collections.abc import Callable
from typing import Any

from fastapi.dependencies import utils

_Signature = Callable[..., inspect.Signature]


def _memoised(original: _Signature) -> _Signature:
    cached = functools.cache(original)

    @functools.wraps(original)
    def get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
        try:
            return cached(call)
        except TypeError:
            # An unhashable callable (an instance with `__call__` and `__eq__`).
            return original(call)

    get_typed_signature.cached = True  # type: ignore[attr-defined]
    return get_typed_signature


def install() -> None:
    """Analyse each dependency's signature once instead of once per route.

    FastAPI inspects a callable's signature, and resolves its annotations, every
    time a route depends on it. Shared dependencies (the session factory, the access
    guard) sit under almost every route, so that work repeated tens of thousands of
    times and took about half of the start-up import time on a small device.

    Must run before any router module is imported. Idempotent.
    """
    if getattr(utils.get_typed_signature, "cached", False):
        return
    utils.get_typed_signature = _memoised(utils.get_typed_signature)
